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

/*
 * ChipDip RDC2-0064 logic analyzer (32 channels, up to 72MHz).
 *
 * Hardware: STM32F722 @216MHz with an external USB HS PHY. The device
 * enumerates as a CDC-ACM serial port (VID 0x0483, PID 0xa210) and needs no
 * vendor driver on Linux/macOS. Channels 0-15 are sampled by TIM1+DMA2,
 * channels 16-31 by TIM8+DMA2, and an external EDGE input (TIM2) can start
 * or gate the whole capture. Sample memory is 240640 bytes.
 *
 * Protocol summary (the authoritative description including all firmware
 * quirks is docs/protocol.md of the OpenLA project,
 * https://github.com/BrLumen/OpenLA):
 *
 *  - Host to device: always exactly 64 bytes, zero padded, written in one
 *    go. Byte 0 selects the module, byte 1 the command, byte 2 is unused,
 *    the payload starts at byte 3.
 *  - Device to host: always 512 bytes, except LA_CMD_GET_SAMPLES which
 *    answers with 240640 bytes in buffer mode and 16384 bytes in stream
 *    mode. LA_CMD_CONFIG produces no reply at all.
 *  - Strict request/response: a second command must never be sent while a
 *    reply is still in flight, otherwise the firmware deadlocks until the
 *    device is power cycled.
 *  - The firmware never sends unsolicited data.
 *
 * Capture modes:
 *
 *  - Buffer mode: LA_CMD_CONFIG starts (or arms) the capture, the host
 *    polls SYS_CMD_GET_STATUS until LA_SAMPLING_CMP is set, then reads the
 *    whole 240640-byte buffer with LA_CMD_GET_SAMPLES and de-interleaves it
 *    (the DMA streams write separate contiguous regions).
 *  - Stream mode: LA_CMD_CONFIG starts a free running capture, each
 *    LA_CMD_GET_SAMPLES blocks in the device until one 16384-byte packet is
 *    ready. LA_CMD_SAMPLE_STOP ends the capture and reports the overflow
 *    flag plus the number of valid packets. SYS_CMD_GET_STATUS must not be
 *    used while a stream capture runs.
 *
 * There is no pre-trigger memory: sampling starts when the trigger fires.
 */

#ifndef LIBSIGROK_HARDWARE_CHIPDIP_RDC2_0064_PROTOCOL_H
#define LIBSIGROK_HARDWARE_CHIPDIP_RDC2_0064_PROTOCOL_H

#include <config.h>
#include <glib.h>
#include <stdint.h>
#include <libsigrok/libsigrok.h>
#include "libsigrok-internal.h"

#define LOG_PREFIX "chipdip-rdc2-0064"

#define RDC2_USB_VID			0x0483
#define RDC2_USB_PID			0xa210

#define RDC2_VENDOR			"ChipDip"
#define RDC2_MODEL			"RDC2-0064"

/* The firmware ignores line coding, DTR and RTS; any setting works. */
#define RDC2_SERIALCOMM			"115200/8n1/dtr=1/rts=0/flow=0"

/* Transport (spec 2). */
#define RDC2_CMD_SIZE			64
#define RDC2_REPLY_SIZE			512
#define RDC2_BUFFER_REPLY_SIZE		240640
#define RDC2_STREAM_PACKET_SIZE		16384

/* Sample memory, and the largest capture the vendor software permits. */
#define RDC2_SAMPLE_MEM_SIZE		240640
#define RDC2_SAMPLE_MEM_USABLE		240000

/* Timer clock of TIM1/TIM8 (spec 5.2). */
#define RDC2_TIMER_CLOCK_HZ		SR_MHZ(216)

#define RDC2_MAX_CHANNELS		32
#define RDC2_CHANNELS_PER_GROUP		8

/* NDTR is 16 bit; the vendor splits captures across DMA streams (spec 5.2). */
#define RDC2_MAX_SAMPLES_PER_STREAM	65000
/* Host-side stream limit of the vendor software (spec 5.3). */
#define RDC2_STREAM_MAX_SAMPLES		16000000000ULL
#define RDC2_MAX_DMA_STREAMS		5

/* Packet header (spec 3). */
#define RDC2_OFF_MODULE_ID		0
#define RDC2_OFF_CMD			1
#define RDC2_OFF_SUBCMD			2
#define RDC2_OFF_DATA			3

/* SYS_CMD_GET_ID reply (spec 4.1). */
#define RDC2_OFF_ID_CONTROLLER		3
#define RDC2_OFF_ID_FIRMWARE		4
#define RDC2_ID_FIRMWARE_SIZE		4
#define RDC2_OFF_ID_MEMORY		8
#define RDC2_OFF_ID_HARDWARE		10
#define RDC2_CONTROLLER_ID		5

/* SYS_CMD_GET_STATUS reply (spec 4.2). */
#define RDC2_OFF_STATUS_BITS		3
#define RDC2_OFF_STATUS_NDTR		4
#define RDC2_STATUS_TRIGGER_AWAIT	(1 << 0)
#define RDC2_STATUS_SAMPLING_CMP	(1 << 1)

/* LA_CMD_CONFIG payload (spec 5.1). */
#define RDC2_OFF_CFG_MODE		3
#define RDC2_OFF_CFG_CHANNELS		4
#define RDC2_OFF_CFG_SAMPLE_COUNT	5
#define RDC2_OFF_CFG_CLOCK_SOURCE	9
#define RDC2_OFF_CFG_PLL_RECONFIG	10
#define RDC2_OFF_CFG_PLL_M		11
#define RDC2_OFF_CFG_PLL_N		12
#define RDC2_OFF_CFG_PLL_P		14
#define RDC2_OFF_CFG_TIM_PSC		15
#define RDC2_OFF_CFG_TIM_ARR		17
#define RDC2_OFF_CFG_DMA_STREAMS	19
#define RDC2_OFF_CFG_TRIG_ACTIVE	20
#define RDC2_OFF_CFG_TRIG_PSC		21
#define RDC2_OFF_CFG_TRIG_ARR		23
#define RDC2_OFF_CFG_CH_TRIGGERS	25
#define RDC2_OFF_CFG_EDGE_TRIGGER	57

/* LA_CMD_SAMPLE_STOP reply (spec 5). */
#define RDC2_OFF_STOP_OVERFLOW		0
#define RDC2_OFF_STOP_PACKETS		1

/* Only the internal timer is implemented by firmware v0.2 (spec 5.1). */
#define RDC2_CLOCK_SOURCE_INTERNAL	0

/* Modules (spec 3). */
enum rdc2_module {
	RDC2_MODULE_SYSTEM = 0,
	RDC2_MODULE_LA = 1,
	RDC2_MODULE_PWM = 2,
	RDC2_MODULE_PWM_INPUT = 3,
};

/* MODULE_SYSTEM commands (spec 4). */
enum rdc2_sys_cmd {
	RDC2_SYS_CMD_GET_ID = 4,
	RDC2_SYS_CMD_GET_STATUS = 5,
};

/* MODULE_LA commands (spec 5). */
enum rdc2_la_cmd {
	RDC2_LA_CMD_CONFIG = 0,
	RDC2_LA_CMD_GET_SAMPLES = 1,
	RDC2_LA_CMD_SAMPLE_STOP = 2,
};

/* Sampling modes (spec 5.1). */
enum rdc2_sampling_mode {
	RDC2_MODE_BUFFER = 0,
	RDC2_MODE_STREAM = 1,
};

/*
 * Trigger type values, used both for the 32 per-channel trigger bytes and
 * for the external EDGE input (spec 5.4).
 *
 * Mapping to libsigrok trigger matches, per trigger kind:
 *
 *   device value        channels 0-15   channels 16-31   EDGE input
 *   -----------------   -------------   --------------   -------------------
 *   RDC2_TRIG_NONE      (no match)      (no match)       unused
 *   RDC2_TRIG_LOW       SR_TRIGGER_ZERO SR_TRIGGER_ZERO  gated: sample while low
 *   RDC2_TRIG_HIGH      SR_TRIGGER_ONE  SR_TRIGGER_ONE   gated: sample while high
 *   RDC2_TRIG_RISING    SR_TRIGGER_RISING  ignored by fw start on rising edge
 *   RDC2_TRIG_FALLING   SR_TRIGGER_FALLING ignored by fw start on falling edge
 *   RDC2_TRIG_EDGE      SR_TRIGGER_EDGE    ignored by fw start on any edge
 *
 * The two gated EDGE modes have no libsigrok equivalent and are not exposed
 * yet; SR_CONF_TRIGGER_SLOPE selects between the rising and falling edge of
 * the EDGE input.
 */
enum rdc2_trigger_type {
	RDC2_TRIG_NONE = 0,
	RDC2_TRIG_LOW = 1,
	RDC2_TRIG_HIGH = 2,
	RDC2_TRIG_RISING = 3,
	RDC2_TRIG_FALLING = 4,
	RDC2_TRIG_EDGE = 5,
};

/* SR_CONF_DATA_SOURCE: forces the capture mode, or leaves the choice to us. */
enum rdc2_data_source {
	RDC2_DATA_SOURCE_AUTO = 0,
	RDC2_DATA_SOURCE_BUFFER,
	RDC2_DATA_SOURCE_STREAM,
};

/* SR_CONF_TRIGGER_SOURCE: whether the external EDGE input takes part. */
enum rdc2_trigger_source {
	RDC2_TRIGGER_SOURCE_CH = 0,
	RDC2_TRIGGER_SOURCE_EXT,
};

/* SR_CONF_TRIGGER_SLOPE: active edge of the external EDGE input. */
enum rdc2_edge_slope {
	RDC2_SLOPE_RISING = 0,
	RDC2_SLOPE_FALLING,
};

/* Acquisition state machine, driven by the fd and timer event sources. */
enum rdc2_state {
	RDC2_STATE_IDLE = 0,
	/* Buffer mode: capture running, GET_STATUS poll due periodically. */
	RDC2_STATE_BUF_POLL,
	/* Buffer mode: GET_STATUS sent, collecting the 512-byte reply. */
	RDC2_STATE_BUF_STATUS,
	/* Buffer mode: GET_SAMPLES sent, collecting 240640 bytes. */
	RDC2_STATE_BUF_SAMPLES,
	/* Stream mode: GET_SAMPLES sent, collecting one 16384-byte packet. */
	RDC2_STATE_STREAM_PACKET,
	/* SAMPLE_STOP sent, collecting the 512-byte reply. */
	RDC2_STATE_STOP_REPLY,
	/* Acquisition finished, sources removed. */
	RDC2_STATE_DONE,
};

/* One entry of the vendor sample rate table (spec 5.2). */
struct rdc2_samplerate {
	uint64_t rate;
	/* Timer prescaler divider; the register gets divider - 1. */
	uint16_t divider;
	/* Timer period of a single DMA stream. */
	uint16_t arr1;
	/* Lowest DMA stream count that sustains this rate. */
	uint8_t min_streams;
};

/* Result of SYS_CMD_GET_ID (spec 4.1). */
struct rdc2_device_id {
	uint8_t controller_id;
	uint8_t firmware[RDC2_ID_FIRMWARE_SIZE];
	uint16_t memory_size;
	uint8_t hardware;
};

/* Everything derived from the user settings when acquisition starts. */
struct rdc2_capture {
	enum rdc2_sampling_mode mode;
	/* Channel mode as sent to the device: 8, 16 or 32. */
	unsigned int num_channels;
	/* Bytes per sample word: 1, 2 or 4. */
	unsigned int unitsize;
	const struct rdc2_samplerate *rate;
	/* Buffer mode only, already normalised for the DMA stream count. */
	uint32_t sample_count;
	uint8_t dma_streams;
	uint8_t ch_triggers[RDC2_MAX_CHANNELS];
	uint8_t edge_trigger;
	gboolean triggers_active;
};

struct dev_context {
	/* User settings. */
	uint64_t cur_samplerate;
	uint64_t limit_samples;
	enum rdc2_data_source data_source;
	enum rdc2_trigger_source trigger_source;
	enum rdc2_edge_slope trigger_slope;

	struct rdc2_capture cap;

	/* Acquisition state machine. */
	enum rdc2_state state;
	gboolean sources_added;
	gboolean stop_req;
	gboolean send_trigger;
	/* Reply accumulator; rx_want is 0 while no reply is outstanding. */
	uint8_t *rx_buf;
	size_t rx_alloc;
	size_t rx_want;
	size_t rx_len;
	unsigned int rx_timeout_ms;
	int64_t rx_deadline;
	int64_t poll_due;
	/* Scratch buffer for de-interleaved samples handed to the session. */
	uint8_t *feed_buf;
	size_t feed_alloc;
	uint64_t samples_sent;
	uint64_t stream_packets;
};

/* Sample rate table (protocol.c). */
SR_PRIV const uint64_t *rdc2_samplerate_list(const struct sr_dev_inst *sdi,
	size_t *count);
SR_PRIV const struct rdc2_samplerate *rdc2_samplerate_find(uint64_t rate);

/* Capture parameter helpers. */
SR_PRIV int rdc2_max_enabled_channel(const struct sr_dev_inst *sdi);
SR_PRIV void rdc2_sample_limits(const struct sr_dev_inst *sdi,
	uint64_t *min_samples, uint64_t *max_samples);
SR_PRIV unsigned int rdc2_channel_mode(unsigned int max_channel_index);
SR_PRIV unsigned int rdc2_unitsize(unsigned int num_channels);
SR_PRIV uint64_t rdc2_max_samplerate(unsigned int num_channels,
	enum rdc2_sampling_mode mode);
SR_PRIV uint64_t rdc2_buffer_capacity(unsigned int num_channels,
	uint64_t samplerate);
SR_PRIV uint8_t rdc2_dma_streams(uint64_t sample_count,
	const struct rdc2_samplerate *rate);
SR_PRIV uint64_t rdc2_stream_samples_per_packet(unsigned int num_channels);
SR_PRIV unsigned int rdc2_stream_timeout_ms(const struct rdc2_capture *cap);

/* Packet builders and parsers. */
SR_PRIV void rdc2_packet_init(uint8_t *packet, uint8_t module, uint8_t cmd);
SR_PRIV void rdc2_build_config_packet(const struct rdc2_capture *cap,
	uint8_t *packet);
SR_PRIV int rdc2_parse_id(const uint8_t *reply, struct rdc2_device_id *id);
SR_PRIV void rdc2_parse_status(const uint8_t *reply, uint8_t *bits,
	uint16_t *ndtr);
SR_PRIV void rdc2_parse_stop(const uint8_t *reply, uint8_t *overflow,
	uint32_t *packets);

/* Sample data conversion. */
SR_PRIV size_t rdc2_deinterleave_buffer(const struct rdc2_capture *cap,
	const uint8_t *src, size_t srclen, uint8_t *dst);
SR_PRIV size_t rdc2_decode_stream_packet(const struct rdc2_capture *cap,
	const uint8_t *src, uint8_t *dst);

/* Transport. */
SR_PRIV int rdc2_send_command(struct sr_serial_dev_inst *serial,
	uint8_t module, uint8_t cmd);
SR_PRIV int rdc2_send_packet(struct sr_serial_dev_inst *serial,
	const uint8_t *packet);
SR_PRIV int rdc2_probe(struct sr_serial_dev_inst *serial,
	struct rdc2_device_id *id);

/* Acquisition. */
SR_PRIV int rdc2_setup_capture(const struct sr_dev_inst *sdi);
SR_PRIV int rdc2_start_acquisition(const struct sr_dev_inst *sdi);
SR_PRIV int rdc2_stop_acquisition(const struct sr_dev_inst *sdi);
SR_PRIV int rdc2_receive_data(int fd, int revents, void *cb_data);
SR_PRIV int rdc2_timer_tick(int fd, int revents, void *cb_data);

#endif
