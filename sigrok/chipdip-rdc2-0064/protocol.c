/*
 * This file is part of the libsigrok project.
 *
 * Copyright (C) 2026 BrLumen
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

#include <config.h>
#include <inttypes.h>
#include <string.h>
#include "protocol.h"

/* Timeouts and intervals, all in milliseconds. */
#define RDC2_WRITE_TIMEOUT_MS		100
#define RDC2_STATUS_TIMEOUT_MS		2000
#define RDC2_BUFFER_TIMEOUT_MS		5000
#define RDC2_STOP_TIMEOUT_MS		2000
#define RDC2_ID_TIMEOUT_MS		1000
#define RDC2_DRAIN_TIMEOUT_MS		2000
#define RDC2_DRAIN_IDLE_MS		200
#define RDC2_POLL_INTERVAL_MS		100
#define RDC2_TIMER_INTERVAL_MS		100

/* Samples handed to the session bus in one SR_DF_LOGIC packet. */
#define RDC2_FEED_CHUNK_SAMPLES		16384

/*
 * Sample rates supported by the vendor software (spec 5.2). The timer
 * prescaler register gets divider - 1, the period register gets
 * arr1 * dma_streams - 1, so the resulting rate is
 *
 *   f = 216MHz / divider / arr1
 *
 * min_streams is the smallest DMA stream count that keeps up with the rate:
 * one stream saturates at ~36MHz.
 */
static const struct rdc2_samplerate samplerates[] = {
	{ SR_KHZ(10),	10800,	2,	1 },
	{ SR_KHZ(20),	5400,	2,	1 },
	{ SR_KHZ(50),	2160,	2,	1 },
	{ SR_KHZ(100),	1080,	2,	1 },
	{ SR_KHZ(200),	540,	2,	1 },
	{ SR_KHZ(500),	216,	2,	1 },
	{ SR_MHZ(1),	108,	2,	1 },
	{ SR_MHZ(2),	54,	2,	1 },
	{ SR_MHZ(4),	27,	2,	1 },
	{ SR_MHZ(8),	9,	3,	1 },
	{ SR_MHZ(12),	9,	2,	1 },
	{ SR_MHZ(18),	6,	2,	1 },
	{ SR_MHZ(24),	3,	3,	1 },
	{ SR_MHZ(36),	3,	2,	1 },
	{ SR_MHZ(54),	2,	2,	4 },
	{ SR_MHZ(72),	1,	3,	4 },
	/*
	 * 108MHz is flagged as experimental by the vendor software: it needs
	 * all five DMA streams and works with at most 30000 samples on eight
	 * channels.
	 */
	{ SR_MHZ(108),	2,	1,	5 },
};

static uint64_t samplerate_values[ARRAY_SIZE(samplerates)];

SR_PRIV const uint64_t *rdc2_samplerate_list(size_t *count)
{
	size_t i;

	for (i = 0; i < ARRAY_SIZE(samplerates); i++)
		samplerate_values[i] = samplerates[i].rate;
	*count = ARRAY_SIZE(samplerates);

	return samplerate_values;
}

SR_PRIV const struct rdc2_samplerate *rdc2_samplerate_find(uint64_t rate)
{
	size_t i;

	for (i = 0; i < ARRAY_SIZE(samplerates); i++) {
		if (samplerates[i].rate == rate)
			return &samplerates[i];
	}

	return NULL;
}

/*
 * The device samples whole banks of channels. Channel mode 24 exists but is
 * broken in firmware v0.2 (spec 6.4), so anything above 16 uses 32 channels.
 */
SR_PRIV unsigned int rdc2_channel_mode(unsigned int max_channel_index)
{
	if (max_channel_index < 8)
		return 8;
	if (max_channel_index < 16)
		return 16;

	return 32;
}

SR_PRIV unsigned int rdc2_unitsize(unsigned int num_channels)
{
	return num_channels / 8;
}

/* Rate limits enforced by the vendor software (spec 5.3). */
SR_PRIV uint64_t rdc2_max_samplerate(unsigned int num_channels,
	enum rdc2_sampling_mode mode)
{
	if (mode == RDC2_MODE_STREAM) {
		switch (num_channels) {
		case 8:
			return SR_MHZ(18);
		case 16:
			return SR_MHZ(8);
		default:
			return SR_MHZ(4);
		}
	}

	switch (num_channels) {
	case 8:
		/* 108MHz is vendor-experimental, see the rate table above. */
		return SR_MHZ(108);
	case 16:
		return SR_MHZ(72);
	default:
		return SR_MHZ(24);
	}
}

SR_PRIV uint64_t rdc2_buffer_capacity(unsigned int num_channels,
	uint64_t samplerate)
{
	uint64_t capacity;

	capacity = RDC2_SAMPLE_MEM_USABLE / rdc2_unitsize(num_channels);

	/* The 108MHz preset only sustains 30000 samples (spec 5.3). */
	if (samplerate > SR_MHZ(72) && capacity > 30000)
		capacity = 30000;

	return capacity;
}

/*
 * Pick the DMA stream count (spec 5.2): enough streams to keep every NDTR
 * below 16 bits, and enough to keep up with the sample rate. Only 1, 4 and 5
 * streams are implemented by the firmware.
 */
SR_PRIV uint8_t rdc2_dma_streams(uint64_t sample_count,
	const struct rdc2_samplerate *rate)
{
	uint64_t by_count;
	uint8_t streams;

	by_count = (sample_count + RDC2_MAX_SAMPLES_PER_STREAM - 1) /
		RDC2_MAX_SAMPLES_PER_STREAM;
	if (by_count < 1)
		by_count = 1;
	if (by_count > RDC2_MAX_DMA_STREAMS)
		by_count = RDC2_MAX_DMA_STREAMS;

	streams = (uint8_t)by_count;
	if (streams < rate->min_streams)
		streams = rate->min_streams;
	if (streams == 2 || streams == 3)
		streams = 4;

	return streams;
}

SR_PRIV uint64_t rdc2_stream_samples_per_packet(unsigned int num_channels)
{
	return RDC2_STREAM_PACKET_SIZE / rdc2_unitsize(num_channels);
}

/*
 * GET_SAMPLES blocks in the device until a whole stream packet was sampled
 * (spec 5.5), so the read timeout has to follow the sample rate.
 */
SR_PRIV unsigned int rdc2_stream_timeout_ms(const struct rdc2_capture *cap)
{
	uint64_t samples, packet_ms, timeout_ms;

	samples = rdc2_stream_samples_per_packet(cap->num_channels);
	packet_ms = samples * 1000 / cap->rate->rate;
	timeout_ms = 2 * packet_ms + 1000;
	if (timeout_ms < 2000)
		timeout_ms = 2000;

	return (unsigned int)timeout_ms;
}

SR_PRIV void rdc2_packet_init(uint8_t *packet, uint8_t module, uint8_t cmd)
{
	memset(packet, 0, RDC2_CMD_SIZE);
	packet[RDC2_OFF_MODULE_ID] = module;
	packet[RDC2_OFF_CMD] = cmd;
	packet[RDC2_OFF_SUBCMD] = 0;
}

SR_PRIV void rdc2_build_config_packet(const struct rdc2_capture *cap,
	uint8_t *packet)
{
	size_t i;

	rdc2_packet_init(packet, RDC2_MODULE_LA, RDC2_LA_CMD_CONFIG);

	packet[RDC2_OFF_CFG_MODE] = (uint8_t)cap->mode;
	packet[RDC2_OFF_CFG_CHANNELS] = (uint8_t)cap->num_channels;
	write_u32le(&packet[RDC2_OFF_CFG_SAMPLE_COUNT], cap->sample_count);
	packet[RDC2_OFF_CFG_CLOCK_SOURCE] = RDC2_CLOCK_SOURCE_INTERNAL;
	/* PLL fields are unused by firmware v0.2 and stay zero. */
	write_u16le(&packet[RDC2_OFF_CFG_TIM_PSC], cap->rate->divider - 1);
	write_u16le(&packet[RDC2_OFF_CFG_TIM_ARR], cap->rate->arr1);
	packet[RDC2_OFF_CFG_DMA_STREAMS] = cap->dma_streams;
	packet[RDC2_OFF_CFG_TRIG_ACTIVE] = cap->triggers_active ? 1 : 0;
	/* The trigger timer fields are unused by firmware v0.2. */
	for (i = 0; i < RDC2_MAX_CHANNELS; i++)
		packet[RDC2_OFF_CFG_CH_TRIGGERS + i] = cap->ch_triggers[i];
	packet[RDC2_OFF_CFG_EDGE_TRIGGER] = cap->edge_trigger;
}

SR_PRIV int rdc2_parse_id(const uint8_t *reply, struct rdc2_device_id *id)
{
	if (reply[RDC2_OFF_MODULE_ID] != RDC2_MODULE_SYSTEM ||
			reply[RDC2_OFF_CMD] != RDC2_SYS_CMD_GET_ID) {
		sr_dbg("Unexpected reply header 0x%02x 0x%02x.",
			reply[RDC2_OFF_MODULE_ID], reply[RDC2_OFF_CMD]);
		return SR_ERR;
	}

	id->controller_id = reply[RDC2_OFF_ID_CONTROLLER];
	memcpy(id->firmware, &reply[RDC2_OFF_ID_FIRMWARE],
		RDC2_ID_FIRMWARE_SIZE);
	id->memory_size = read_u16le(&reply[RDC2_OFF_ID_MEMORY]);
	id->hardware = reply[RDC2_OFF_ID_HARDWARE];

	if (id->controller_id != RDC2_CONTROLLER_ID) {
		sr_dbg("Unexpected controller id %u.", id->controller_id);
		return SR_ERR;
	}

	return SR_OK;
}

SR_PRIV void rdc2_parse_status(const uint8_t *reply, uint8_t *bits,
	uint16_t *ndtr)
{
	*bits = reply[RDC2_OFF_STATUS_BITS];
	*ndtr = read_u16le(&reply[RDC2_OFF_STATUS_NDTR]);
}

SR_PRIV void rdc2_parse_stop(const uint8_t *reply, uint8_t *overflow,
	uint32_t *packets)
{
	*overflow = reply[RDC2_OFF_STOP_OVERFLOW];
	*packets = read_u32le(&reply[RDC2_OFF_STOP_PACKETS]);
}

/*
 * De-interleave a buffer mode capture (spec 6.1). Every DMA stream writes its
 * own contiguous part of the buffer, holding samples k, k + N, k + 2N, ... of
 * channels 0-15. With 32 channels an extra part with the samples of channels
 * 16-31 follows.
 *
 * Returns the number of bytes written to dst, or 0 if src is too short.
 */
SR_PRIV size_t rdc2_deinterleave_buffer(const struct rdc2_capture *cap,
	const uint8_t *src, size_t srclen, uint8_t *dst)
{
	size_t bps, per_stream, part_size, needed, i, k;
	uint8_t *out;

	bps = (cap->num_channels == 8) ? 1 : 2;
	per_stream = cap->sample_count / cap->dma_streams;
	part_size = per_stream * bps;

	needed = cap->dma_streams * part_size;
	if (cap->num_channels == 32)
		needed += per_stream * 2;
	if (needed > srclen) {
		sr_err("Sample buffer too short: %zu of %zu bytes.",
			srclen, needed);
		return 0;
	}

	/* One stream and at most 16 channels is already in sample order. */
	if (cap->dma_streams == 1 && cap->num_channels <= 16) {
		memcpy(dst, src, needed);
		return needed;
	}

	out = dst;
	for (i = 0; i < per_stream; i++) {
		for (k = 0; k < cap->dma_streams; k++) {
			memcpy(out, src + k * part_size + i * bps, bps);
			out += bps;
		}
		if (cap->num_channels == 32) {
			memcpy(out, src + cap->dma_streams * part_size + i * 2, 2);
			out += 2;
		}
	}

	return (size_t)(out - dst);
}

/*
 * Convert one stream mode packet (spec 6.2). Eight and 16 channel packets are
 * already in sample order; 32 channel packets hold the two 16-bit halves in
 * separate halves of the packet and need interleaving into 32-bit words.
 *
 * Returns the number of bytes written to dst.
 */
SR_PRIV size_t rdc2_decode_stream_packet(const struct rdc2_capture *cap,
	const uint8_t *src, uint8_t *dst)
{
	size_t samples, i, half;

	if (cap->num_channels != 32) {
		memcpy(dst, src, RDC2_STREAM_PACKET_SIZE);
		return RDC2_STREAM_PACKET_SIZE;
	}

	half = RDC2_STREAM_PACKET_SIZE / 2;
	samples = half / 2;
	for (i = 0; i < samples; i++) {
		dst[i * 4 + 0] = src[i * 2 + 0];
		dst[i * 4 + 1] = src[i * 2 + 1];
		dst[i * 4 + 2] = src[half + i * 2 + 0];
		dst[i * 4 + 3] = src[half + i * 2 + 1];
	}

	return RDC2_STREAM_PACKET_SIZE;
}

SR_PRIV int rdc2_send_packet(struct sr_serial_dev_inst *serial,
	const uint8_t *packet)
{
	int ret;

	/* Spec 2.1: the firmware expects one full 64-byte bulk OUT packet. */
	ret = serial_write_blocking(serial, packet, RDC2_CMD_SIZE,
		RDC2_WRITE_TIMEOUT_MS);
	if (ret < 0)
		return ret;
	if (ret != RDC2_CMD_SIZE) {
		sr_err("Short command write (%d of %d bytes).",
			ret, RDC2_CMD_SIZE);
		return SR_ERR_IO;
	}

	return SR_OK;
}

SR_PRIV int rdc2_send_command(struct sr_serial_dev_inst *serial,
	uint8_t module, uint8_t cmd)
{
	uint8_t packet[RDC2_CMD_SIZE];

	rdc2_packet_init(packet, module, cmd);

	return rdc2_send_packet(serial, packet);
}

/*
 * Read and discard whatever the device sends, until it went quiet for
 * RDC2_DRAIN_IDLE_MS or the total budget ran out. Returns the number of
 * bytes discarded.
 */
static size_t rdc2_drain(struct sr_serial_dev_inst *serial,
	unsigned int timeout_ms)
{
	uint8_t scrap[RDC2_REPLY_SIZE];
	int64_t deadline, idle_since, now;
	size_t total, avail;
	int len;

	total = 0;
	now = g_get_monotonic_time();
	deadline = now + 1000LL * timeout_ms;
	idle_since = now;

	while (now < deadline) {
		avail = serial_has_receive_data(serial);
		if (avail > sizeof(scrap))
			avail = sizeof(scrap);
		if (avail) {
			len = serial_read_nonblocking(serial, scrap, avail);
			if (len > 0) {
				total += len;
				idle_since = now;
				now = g_get_monotonic_time();
				continue;
			}
		}
		if (total >= RDC2_REPLY_SIZE &&
				now - idle_since > 1000LL * RDC2_DRAIN_IDLE_MS)
			break;
		g_usleep(10 * 1000);
		now = g_get_monotonic_time();
	}

	return total;
}

/*
 * Identify the device on an already opened port, following the recommended
 * open sequence of spec 7.3.
 */
SR_PRIV int rdc2_probe(struct sr_serial_dev_inst *serial,
	struct rdc2_device_id *id)
{
	uint8_t reply[RDC2_REPLY_SIZE];
	size_t drained;
	int ret, len;

	serial_flush(serial);

	/*
	 * Stop a capture that may still be running from an earlier session.
	 * An unfinished 16384-byte stream packet can precede the 512-byte
	 * reply, so everything that arrives is discarded.
	 */
	ret = rdc2_send_command(serial, RDC2_MODULE_LA,
		RDC2_LA_CMD_SAMPLE_STOP);
	if (ret != SR_OK)
		return ret;

	drained = rdc2_drain(serial, RDC2_DRAIN_TIMEOUT_MS);
	if (drained < RDC2_REPLY_SIZE) {
		sr_dbg("No reply to SAMPLE_STOP on %s (%zu bytes); either this "
			"is not an RDC2-0064 or its firmware is stuck and the "
			"device needs to be replugged.", serial->port, drained);
		return SR_ERR;
	}
	serial_flush(serial);

	ret = rdc2_send_command(serial, RDC2_MODULE_SYSTEM,
		RDC2_SYS_CMD_GET_ID);
	if (ret != SR_OK)
		return ret;

	len = serial_read_blocking(serial, reply, sizeof(reply),
		RDC2_ID_TIMEOUT_MS);
	if (len != RDC2_REPLY_SIZE) {
		sr_dbg("Got %d of %d ID reply bytes from %s.",
			len, RDC2_REPLY_SIZE, serial->port);
		return SR_ERR;
	}

	return rdc2_parse_id(reply, id);
}

/* Translate the session trigger into the per-channel trigger bytes. */
static int rdc2_convert_trigger(const struct sr_dev_inst *sdi)
{
	struct dev_context *devc;
	struct rdc2_capture *cap;
	struct sr_trigger *trigger;
	struct sr_trigger_stage *stage;
	struct sr_trigger_match *match;
	GSList *l;
	uint8_t type;
	int idx;

	devc = sdi->priv;
	cap = &devc->cap;

	memset(cap->ch_triggers, 0, sizeof(cap->ch_triggers));
	cap->triggers_active = FALSE;
	cap->edge_trigger = RDC2_TRIG_NONE;

	if (devc->trigger_source == RDC2_TRIGGER_SOURCE_EXT) {
		cap->edge_trigger = (devc->trigger_slope == RDC2_SLOPE_FALLING)
			? RDC2_TRIG_FALLING : RDC2_TRIG_RISING;
	}

	trigger = sr_session_trigger_get(sdi->session);
	if (!trigger || !trigger->stages)
		return SR_OK;

	if (trigger->stages->next) {
		sr_err("This device only supports a single trigger stage.");
		return SR_ERR_NA;
	}
	stage = trigger->stages->data;

	for (l = stage->matches; l; l = l->next) {
		match = l->data;
		if (!match->channel)
			continue;
		if (!match->channel->enabled) {
			sr_warn("Ignoring the trigger on disabled channel %s.",
				match->channel->name);
			continue;
		}
		idx = match->channel->index;
		if (idx < 0 || (unsigned int)idx >= cap->num_channels) {
			sr_err("Trigger on channel %s is outside the active "
				"%u-channel mode.", match->channel->name,
				cap->num_channels);
			return SR_ERR_ARG;
		}

		switch (match->match) {
		case SR_TRIGGER_ZERO:
			type = RDC2_TRIG_LOW;
			break;
		case SR_TRIGGER_ONE:
			type = RDC2_TRIG_HIGH;
			break;
		case SR_TRIGGER_RISING:
			type = RDC2_TRIG_RISING;
			break;
		case SR_TRIGGER_FALLING:
			type = RDC2_TRIG_FALLING;
			break;
		case SR_TRIGGER_EDGE:
			type = RDC2_TRIG_EDGE;
			break;
		default:
			sr_err("Unsupported trigger match %d on channel %s.",
				match->match, match->channel->name);
			return SR_ERR_ARG;
		}

		/* Spec 5.4: channels 16-31 only reach the level comparators. */
		if (type >= RDC2_TRIG_RISING && idx >= 16) {
			sr_err("Edge triggers are not available on channel %s; "
				"channels 16-31 support level triggers only.",
				match->channel->name);
			return SR_ERR_ARG;
		}

		cap->ch_triggers[idx] = type;
		cap->triggers_active = TRUE;
	}

	return SR_OK;
}

/* Derive every capture parameter from the current settings. */
SR_PRIV int rdc2_setup_capture(const struct sr_dev_inst *sdi)
{
	struct dev_context *devc;
	struct rdc2_capture *cap;
	struct sr_channel *ch;
	GSList *l;
	uint64_t capacity, max_rate, count;
	int max_index;
	int ret;

	devc = sdi->priv;
	cap = &devc->cap;
	memset(cap, 0, sizeof(*cap));

	max_index = -1;
	for (l = sdi->channels; l; l = l->next) {
		ch = l->data;
		if (ch->type != SR_CHANNEL_LOGIC || !ch->enabled)
			continue;
		if (ch->index > max_index)
			max_index = ch->index;
	}
	if (max_index < 0) {
		sr_err("No logic channel is enabled.");
		return SR_ERR;
	}

	cap->num_channels = rdc2_channel_mode(max_index);
	cap->unitsize = rdc2_unitsize(cap->num_channels);

	cap->rate = rdc2_samplerate_find(devc->cur_samplerate);
	if (!cap->rate) {
		sr_err("Samplerate %" PRIu64 " is not supported.",
			devc->cur_samplerate);
		return SR_ERR_SAMPLERATE;
	}

	capacity = rdc2_buffer_capacity(cap->num_channels, cap->rate->rate);

	switch (devc->data_source) {
	case RDC2_DATA_SOURCE_BUFFER:
		cap->mode = RDC2_MODE_BUFFER;
		break;
	case RDC2_DATA_SOURCE_STREAM:
		cap->mode = RDC2_MODE_STREAM;
		break;
	default:
		/* Anything the sample memory cannot hold has to be streamed. */
		cap->mode = (!devc->limit_samples ||
			devc->limit_samples > capacity)
			? RDC2_MODE_STREAM : RDC2_MODE_BUFFER;
		break;
	}

	max_rate = rdc2_max_samplerate(cap->num_channels, cap->mode);
	if (cap->rate->rate > max_rate) {
		sr_err("%s mode with %u channels is limited to %" PRIu64 " Hz, "
			"%" PRIu64 " Hz was requested.",
			(cap->mode == RDC2_MODE_STREAM) ? "Stream" : "Buffer",
			cap->num_channels, max_rate, cap->rate->rate);
		return SR_ERR_SAMPLERATE;
	}

	if (cap->mode == RDC2_MODE_STREAM) {
		/* Stream mode always uses a single DMA stream (spec 5.2). */
		cap->dma_streams = 1;
		cap->sample_count = 0;
	} else {
		if (!devc->limit_samples) {
			sr_err("Buffer mode needs a sample limit; use a "
				"sample limit or the Stream data source.");
			return SR_ERR_ARG;
		}
		count = devc->limit_samples;
		if (count > capacity) {
			sr_info("Limiting the capture to %" PRIu64 " samples, "
				"the sample memory holds no more with %u "
				"channels at %" PRIu64 " Hz.", capacity,
				cap->num_channels, cap->rate->rate);
			count = capacity;
		}

		cap->dma_streams = rdc2_dma_streams(count, cap->rate);
		/*
		 * With 32 channels the second DMA only transfers
		 * sample_count / N words (spec 6.4), so the capture has to
		 * stay on a single stream. The rate and sample count limits
		 * above already guarantee this.
		 */
		if (cap->num_channels == 32 && cap->dma_streams != 1) {
			sr_err("32-channel captures need a single DMA stream.");
			return SR_ERR;
		}

		if (count % cap->dma_streams) {
			count -= count % cap->dma_streams;
			if (!count)
				count = cap->dma_streams;
			sr_info("Rounded the sample count to %" PRIu64 ", it "
				"has to be a multiple of the DMA stream count "
				"%u.", count, cap->dma_streams);
		}
		cap->sample_count = (uint32_t)count;
	}

	if ((ret = rdc2_convert_trigger(sdi)) != SR_OK)
		return ret;

	sr_dbg("Capture: %s mode, %u channels, %" PRIu64 " Hz, "
		"%u samples, %u DMA stream(s), triggers %s, EDGE %u.",
		(cap->mode == RDC2_MODE_STREAM) ? "stream" : "buffer",
		cap->num_channels, cap->rate->rate, cap->sample_count,
		cap->dma_streams, cap->triggers_active ? "on" : "off",
		cap->edge_trigger);

	return SR_OK;
}

/* Remove the event sources and end the session's datafeed exactly once. */
static void rdc2_finish(const struct sr_dev_inst *sdi)
{
	struct dev_context *devc;

	devc = sdi->priv;
	if (devc->state == RDC2_STATE_DONE)
		return;

	devc->state = RDC2_STATE_DONE;
	devc->rx_want = 0;
	if (devc->sources_added) {
		serial_source_remove(sdi->session, sdi->conn);
		sr_session_source_remove(sdi->session, -1);
		devc->sources_added = FALSE;
	}

	std_session_send_df_end(sdi);
}

/*
 * Send one command and arm the receive path for its reply. Never call this
 * while another reply is still outstanding (spec 2.3). A rx_deadline of 0
 * disables the watchdog; it is re-armed as soon as the first byte arrives.
 */
static int rdc2_request(const struct sr_dev_inst *sdi, uint8_t module,
	uint8_t cmd, size_t reply_size, unsigned int timeout_ms)
{
	struct dev_context *devc;
	int ret;

	devc = sdi->priv;
	devc->rx_len = 0;
	devc->rx_want = reply_size;
	devc->rx_timeout_ms = timeout_ms;
	devc->rx_deadline = g_get_monotonic_time() + 1000LL * timeout_ms;

	ret = rdc2_send_command(sdi->conn, module, cmd);
	if (ret != SR_OK) {
		devc->rx_want = 0;
		return ret;
	}

	return SR_OK;
}

static int rdc2_send_logic(const struct sr_dev_inst *sdi, const uint8_t *data,
	uint64_t samples)
{
	struct dev_context *devc;
	struct sr_datafeed_packet packet;
	struct sr_datafeed_logic logic;
	uint64_t sent, chunk;
	int ret;

	devc = sdi->priv;

	packet.type = SR_DF_LOGIC;
	packet.payload = &logic;
	logic.unitsize = devc->cap.unitsize;

	for (sent = 0; sent < samples; sent += chunk) {
		chunk = samples - sent;
		if (chunk > RDC2_FEED_CHUNK_SAMPLES)
			chunk = RDC2_FEED_CHUNK_SAMPLES;
		logic.length = chunk * devc->cap.unitsize;
		logic.data = (void *)(data + sent * devc->cap.unitsize);
		if ((ret = sr_session_send(sdi, &packet)) != SR_OK)
			return ret;
	}
	devc->samples_sent += samples;

	return SR_OK;
}

/* There is no pre-trigger memory: sampling starts at the trigger (spec 5.4). */
static void rdc2_send_trigger_marker(const struct sr_dev_inst *sdi)
{
	struct dev_context *devc;

	devc = sdi->priv;
	if (!devc->send_trigger)
		return;

	std_session_send_df_trigger(sdi);
	devc->send_trigger = FALSE;
}

static void rdc2_handle_buffer_status(const struct sr_dev_inst *sdi)
{
	struct dev_context *devc;
	uint8_t bits;
	uint16_t ndtr;

	devc = sdi->priv;
	rdc2_parse_status(devc->rx_buf, &bits, &ndtr);

	if (!(bits & RDC2_STATUS_SAMPLING_CMP)) {
		sr_spew("Capture running, %u transfers left per stream.", ndtr);
		devc->state = RDC2_STATE_BUF_POLL;
		devc->poll_due = g_get_monotonic_time() +
			1000LL * RDC2_POLL_INTERVAL_MS;
		return;
	}

	if (rdc2_request(sdi, RDC2_MODULE_LA, RDC2_LA_CMD_GET_SAMPLES,
			RDC2_BUFFER_REPLY_SIZE, RDC2_BUFFER_TIMEOUT_MS)
			!= SR_OK) {
		sr_err("Failed to request the sample buffer.");
		rdc2_finish(sdi);
		return;
	}
	devc->state = RDC2_STATE_BUF_SAMPLES;
}

static void rdc2_handle_buffer_samples(const struct sr_dev_inst *sdi)
{
	struct dev_context *devc;
	size_t len;

	devc = sdi->priv;

	len = rdc2_deinterleave_buffer(&devc->cap, devc->rx_buf, devc->rx_len,
		devc->feed_buf);
	if (!len) {
		rdc2_finish(sdi);
		return;
	}

	rdc2_send_trigger_marker(sdi);
	rdc2_send_logic(sdi, devc->feed_buf, len / devc->cap.unitsize);
	sr_info("Buffer capture done, %" PRIu64 " samples.",
		devc->samples_sent);
	rdc2_finish(sdi);
}

static void rdc2_handle_stream_packet(const struct sr_dev_inst *sdi)
{
	struct dev_context *devc;
	uint64_t samples, remaining;
	gboolean done;

	devc = sdi->priv;

	rdc2_decode_stream_packet(&devc->cap, devc->rx_buf, devc->feed_buf);
	devc->stream_packets++;

	samples = rdc2_stream_samples_per_packet(devc->cap.num_channels);
	done = devc->stop_req;
	if (devc->limit_samples) {
		remaining = (devc->limit_samples > devc->samples_sent)
			? devc->limit_samples - devc->samples_sent : 0;
		if (samples >= remaining) {
			samples = remaining;
			done = TRUE;
		}
	}

	rdc2_send_trigger_marker(sdi);
	if (samples)
		rdc2_send_logic(sdi, devc->feed_buf, samples);

	if (done) {
		if (rdc2_request(sdi, RDC2_MODULE_LA, RDC2_LA_CMD_SAMPLE_STOP,
				RDC2_REPLY_SIZE, RDC2_STOP_TIMEOUT_MS)
				!= SR_OK) {
			sr_err("Failed to stop the stream capture.");
			rdc2_finish(sdi);
			return;
		}
		devc->state = RDC2_STATE_STOP_REPLY;
		return;
	}

	if (rdc2_request(sdi, RDC2_MODULE_LA, RDC2_LA_CMD_GET_SAMPLES,
			RDC2_STREAM_PACKET_SIZE,
			rdc2_stream_timeout_ms(&devc->cap)) != SR_OK) {
		sr_err("Failed to request the next stream packet.");
		rdc2_finish(sdi);
	}
}

/*
 * An armed trigger delays the very first stream packet for an unbounded
 * amount of time (spec 7.3: GET_SAMPLES blocks in the device until a packet
 * is ready), so the watchdog only starts once the device begins to answer.
 */
static void rdc2_arm_first_stream_packet(const struct sr_dev_inst *sdi)
{
	struct dev_context *devc;

	devc = sdi->priv;
	if (devc->send_trigger)
		devc->rx_deadline = 0;
}

static void rdc2_handle_stop_reply(const struct sr_dev_inst *sdi)
{
	struct dev_context *devc;
	uint8_t overflow;
	uint32_t packets;

	devc = sdi->priv;
	rdc2_parse_stop(devc->rx_buf, &overflow, &packets);

	if (overflow) {
		sr_warn("The device overran its stream buffer; samples after "
			"packet %u are unreliable.", packets);
	}
	sr_info("Stream capture done, %u valid packets, %" PRIu64 " samples.",
		packets, devc->samples_sent);

	rdc2_finish(sdi);
}

static void rdc2_handle_reply(const struct sr_dev_inst *sdi)
{
	struct dev_context *devc;

	devc = sdi->priv;

	switch (devc->state) {
	case RDC2_STATE_BUF_STATUS:
		rdc2_handle_buffer_status(sdi);
		break;
	case RDC2_STATE_BUF_SAMPLES:
		rdc2_handle_buffer_samples(sdi);
		break;
	case RDC2_STATE_STREAM_PACKET:
		rdc2_handle_stream_packet(sdi);
		break;
	case RDC2_STATE_STOP_REPLY:
		rdc2_handle_stop_reply(sdi);
		break;
	default:
		sr_warn("Unexpected reply in state %d.", devc->state);
		break;
	}
}

SR_PRIV int rdc2_receive_data(int fd, int revents, void *cb_data)
{
	struct sr_dev_inst *sdi;
	struct dev_context *devc;
	struct sr_serial_dev_inst *serial;
	uint8_t scrap[RDC2_REPLY_SIZE];
	int len;

	(void)fd;

	if (!(sdi = cb_data) || !(devc = sdi->priv))
		return TRUE;
	if (!(revents & G_IO_IN))
		return TRUE;
	if (devc->state == RDC2_STATE_DONE)
		return TRUE;

	serial = sdi->conn;

	if (!devc->rx_want) {
		/* Spec 2.4: the firmware never sends unsolicited data. */
		len = serial_read_nonblocking(serial, scrap, sizeof(scrap));
		if (len > 0)
			sr_warn("Discarding %d unexpected bytes.", len);
		return TRUE;
	}

	len = serial_read_nonblocking(serial, devc->rx_buf + devc->rx_len,
		devc->rx_want - devc->rx_len);
	if (len < 0) {
		sr_err("Read error on %s.", serial->port);
		rdc2_finish(sdi);
		return TRUE;
	}
	if (len > 0) {
		devc->rx_len += len;
		devc->rx_deadline = g_get_monotonic_time() +
			1000LL * devc->rx_timeout_ms;
	}
	if (devc->rx_len < devc->rx_want)
		return TRUE;

	/* The reply is complete, no request is outstanding any more. */
	devc->rx_want = 0;
	rdc2_handle_reply(sdi);

	return TRUE;
}

SR_PRIV int rdc2_timer_tick(int fd, int revents, void *cb_data)
{
	struct sr_dev_inst *sdi;
	struct dev_context *devc;
	int64_t now;

	(void)fd;
	(void)revents;

	if (!(sdi = cb_data) || !(devc = sdi->priv))
		return TRUE;
	if (devc->state == RDC2_STATE_IDLE || devc->state == RDC2_STATE_DONE)
		return TRUE;

	now = g_get_monotonic_time();

	if (devc->state == RDC2_STATE_BUF_POLL) {
		if (now < devc->poll_due)
			return TRUE;
		/* Only poll while no reply is in flight (spec 2.3). */
		if (rdc2_request(sdi, RDC2_MODULE_SYSTEM,
				RDC2_SYS_CMD_GET_STATUS, RDC2_REPLY_SIZE,
				RDC2_STATUS_TIMEOUT_MS) != SR_OK) {
			sr_err("Failed to request the device status.");
			rdc2_finish(sdi);
			return TRUE;
		}
		devc->state = RDC2_STATE_BUF_STATUS;
		return TRUE;
	}

	/* Watchdog: a reply is outstanding but nothing arrives any more. */
	if (devc->rx_want && devc->rx_deadline && now > devc->rx_deadline) {
		sr_err("Timeout after %u ms, got %zu of %zu reply bytes.",
			devc->rx_timeout_ms, devc->rx_len, devc->rx_want);
		rdc2_finish(sdi);
	}

	return TRUE;
}

SR_PRIV int rdc2_start_acquisition(const struct sr_dev_inst *sdi)
{
	struct dev_context *devc;
	struct sr_serial_dev_inst *serial;
	uint8_t packet[RDC2_CMD_SIZE];
	size_t rx_alloc, feed_alloc;
	int ret;

	devc = sdi->priv;
	serial = sdi->conn;

	if (devc->cap.mode == RDC2_MODE_BUFFER) {
		rx_alloc = RDC2_BUFFER_REPLY_SIZE;
		feed_alloc = (size_t)devc->cap.sample_count * devc->cap.unitsize;
	} else {
		rx_alloc = RDC2_STREAM_PACKET_SIZE;
		feed_alloc = RDC2_STREAM_PACKET_SIZE;
	}
	if (rx_alloc < RDC2_REPLY_SIZE)
		rx_alloc = RDC2_REPLY_SIZE;

	if (devc->rx_alloc < rx_alloc) {
		devc->rx_buf = g_realloc(devc->rx_buf, rx_alloc);
		devc->rx_alloc = rx_alloc;
	}
	if (devc->feed_alloc < feed_alloc) {
		devc->feed_buf = g_realloc(devc->feed_buf, feed_alloc);
		devc->feed_alloc = feed_alloc;
	}

	devc->state = RDC2_STATE_IDLE;
	devc->stop_req = FALSE;
	devc->rx_len = 0;
	devc->rx_want = 0;
	devc->samples_sent = 0;
	devc->stream_packets = 0;
	devc->send_trigger = devc->cap.triggers_active ||
		devc->cap.edge_trigger != RDC2_TRIG_NONE;

	/* Drop leftovers of an earlier session so start/stop cycles work. */
	serial_flush(serial);

	/* LA_CMD_CONFIG has no reply and starts (or arms) the capture. */
	rdc2_build_config_packet(&devc->cap, packet);
	if ((ret = rdc2_send_packet(serial, packet)) != SR_OK) {
		sr_err("Failed to configure the device.");
		return ret;
	}

	std_session_send_df_header(sdi);

	ret = serial_source_add(sdi->session, serial, G_IO_IN, -1,
		rdc2_receive_data, (struct sr_dev_inst *)sdi);
	if (ret != SR_OK)
		return ret;
	ret = sr_session_source_add(sdi->session, -1, 0, RDC2_TIMER_INTERVAL_MS,
		rdc2_timer_tick, (struct sr_dev_inst *)sdi);
	if (ret != SR_OK) {
		serial_source_remove(sdi->session, serial);
		return ret;
	}
	devc->sources_added = TRUE;

	if (devc->cap.mode == RDC2_MODE_BUFFER) {
		devc->state = RDC2_STATE_BUF_POLL;
		devc->poll_due = g_get_monotonic_time() +
			1000LL * RDC2_POLL_INTERVAL_MS;
		return SR_OK;
	}

	/*
	 * Spec 7.3: GET_SAMPLES must only be sent while a stream capture is
	 * running, the capture above has just been started by CONFIG.
	 */
	ret = rdc2_request(sdi, RDC2_MODULE_LA, RDC2_LA_CMD_GET_SAMPLES,
		RDC2_STREAM_PACKET_SIZE, rdc2_stream_timeout_ms(&devc->cap));
	if (ret != SR_OK) {
		rdc2_finish(sdi);
		return ret;
	}
	rdc2_arm_first_stream_packet(sdi);
	devc->state = RDC2_STATE_STREAM_PACKET;

	return SR_OK;
}

SR_PRIV int rdc2_stop_acquisition(const struct sr_dev_inst *sdi)
{
	struct dev_context *devc;
	struct sr_serial_dev_inst *serial;
	uint8_t overflow;
	uint32_t packets;
	int len;

	devc = sdi->priv;
	serial = sdi->conn;

	if (devc->state == RDC2_STATE_IDLE || devc->state == RDC2_STATE_DONE) {
		rdc2_finish(sdi);
		return SR_OK;
	}

	devc->stop_req = TRUE;

	if (devc->state != RDC2_STATE_BUF_POLL &&
			devc->state != RDC2_STATE_BUF_STATUS) {
		/*
		 * A reply is in flight. Two outstanding requests would
		 * deadlock the firmware (spec 2.3), so the state machine
		 * finishes the transfer and stops afterwards.
		 */
		if (devc->state == RDC2_STATE_STREAM_PACKET &&
				devc->send_trigger && !devc->rx_len) {
			sr_warn("The stream trigger has not fired yet and the "
				"firmware cannot cancel a pending GET_SAMPLES "
				"(see docs/protocol.md 7.3); replug the device "
				"if the trigger never arrives.");
		} else {
			sr_dbg("Stop requested, finishing the running transfer.");
		}
		return SR_OK;
	}

	/*
	 * The capture is still running or waiting for its trigger. Consume a
	 * GET_STATUS reply that may still be on its way, then cancel.
	 *
	 * Caveat (spec 7.3): with level-only channel triggers the firmware
	 * busy-waits in its main loop and does not process SAMPLE_STOP before
	 * the trigger condition becomes true. The read below then times out
	 * and the device stays armed until the trigger fires or it is
	 * replugged. Edge triggers do not have this problem.
	 */
	if (devc->rx_want) {
		len = serial_read_blocking(serial, devc->rx_buf + devc->rx_len,
			devc->rx_want - devc->rx_len, RDC2_STATUS_TIMEOUT_MS);
		if (len < 0 || (size_t)len < devc->rx_want - devc->rx_len)
			sr_dbg("Pending status reply was not completed.");
		devc->rx_want = 0;
		devc->rx_len = 0;
	}

	if (rdc2_send_command(serial, RDC2_MODULE_LA, RDC2_LA_CMD_SAMPLE_STOP)
			== SR_OK) {
		len = serial_read_blocking(serial, devc->rx_buf,
			RDC2_REPLY_SIZE, RDC2_STOP_TIMEOUT_MS);
		if (len == RDC2_REPLY_SIZE) {
			rdc2_parse_stop(devc->rx_buf, &overflow, &packets);
			sr_dbg("Capture cancelled, overflow %u, packets %u.",
				overflow, packets);
		} else {
			sr_warn("The device did not acknowledge SAMPLE_STOP; "
				"with level-only triggers it stays armed until "
				"the trigger fires (see docs/protocol.md 7.3).");
		}
	}

	rdc2_finish(sdi);

	return SR_OK;
}
