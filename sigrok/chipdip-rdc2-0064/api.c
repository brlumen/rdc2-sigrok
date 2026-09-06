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

#define RDC2_DEFAULT_SAMPLERATE		SR_MHZ(1)

static const uint32_t scanopts[] = {
	SR_CONF_CONN,
	/* The firmware ignores line settings, but the port has to be opened. */
	SR_CONF_SERIALCOMM,
};

static const uint32_t drvopts[] = {
	SR_CONF_LOGIC_ANALYZER,
};

static const uint32_t devopts[] = {
	SR_CONF_CONN | SR_CONF_GET,
	SR_CONF_SAMPLERATE | SR_CONF_GET | SR_CONF_SET | SR_CONF_LIST,
	SR_CONF_LIMIT_SAMPLES | SR_CONF_GET | SR_CONF_SET | SR_CONF_LIST,
	SR_CONF_CONTINUOUS,
	SR_CONF_TRIGGER_MATCH | SR_CONF_LIST,
	SR_CONF_DATA_SOURCE | SR_CONF_GET | SR_CONF_SET | SR_CONF_LIST,
	SR_CONF_TRIGGER_SOURCE | SR_CONF_GET | SR_CONF_SET | SR_CONF_LIST,
	SR_CONF_TRIGGER_SLOPE | SR_CONF_GET | SR_CONF_SET | SR_CONF_LIST,
};

static const int32_t trigger_matches[] = {
	SR_TRIGGER_ZERO,
	SR_TRIGGER_ONE,
	SR_TRIGGER_RISING,
	SR_TRIGGER_FALLING,
	SR_TRIGGER_EDGE,
};

/* Capture mode: derived from the sample limit, or forced by the user. */
static const char *data_sources[] = {
	[RDC2_DATA_SOURCE_AUTO] = "Auto",
	[RDC2_DATA_SOURCE_BUFFER] = "Buffer",
	[RDC2_DATA_SOURCE_STREAM] = "Stream",
};

/* Whether the external EDGE input takes part in starting the capture. */
static const char *trigger_sources[] = {
	[RDC2_TRIGGER_SOURCE_CH] = "CH",
	[RDC2_TRIGGER_SOURCE_EXT] = "EXT",
};

/* Active edge of the external EDGE input. */
static const char *trigger_slopes[] = {
	[RDC2_SLOPE_RISING] = "r",
	[RDC2_SLOPE_FALLING] = "f",
};

static void clear_helper(void *priv)
{
	struct dev_context *devc;

	devc = priv;
	g_free(devc->rx_buf);
	g_free(devc->feed_buf);
}

static int dev_clear(const struct sr_dev_driver *di)
{
	return std_dev_clear_with_callback(di, clear_helper);
}

static struct sr_dev_inst *probe_port(const char *port, const char *serialcomm)
{
	struct sr_dev_inst *sdi;
	struct sr_serial_dev_inst *serial;
	struct dev_context *devc;
	struct rdc2_device_id id;
	char name[8];
	unsigned int i;
	int ret;

	serial = sr_serial_dev_inst_new(port, serialcomm);
	if (serial_open(serial, SERIAL_RDWR) != SR_OK) {
		sr_serial_dev_inst_free(serial);
		return NULL;
	}

	sr_info("Probing %s.", port);
	ret = rdc2_probe(serial, &id);
	serial_close(serial);
	if (ret != SR_OK) {
		sr_serial_dev_inst_free(serial);
		return NULL;
	}

	sdi = g_malloc0(sizeof(*sdi));
	sdi->status = SR_ST_INACTIVE;
	sdi->inst_type = SR_INST_SERIAL;
	sdi->conn = serial;
	sdi->connection_id = g_strdup(serial->port);
	sdi->vendor = g_strdup(RDC2_VENDOR);
	sdi->model = g_strdup(RDC2_MODEL);
	if (id.firmware[2] || id.firmware[3]) {
		sdi->version = g_strdup_printf("%u.%u.%u.%u", id.firmware[0],
			id.firmware[1], id.firmware[2], id.firmware[3]);
	} else {
		sdi->version = g_strdup_printf("%u.%u", id.firmware[0],
			id.firmware[1]);
	}
	sr_info("Found %s %s, firmware %s, hardware %u.", sdi->vendor,
		sdi->model, sdi->version, id.hardware);

	for (i = 0; i < RDC2_MAX_CHANNELS; i++) {
		g_snprintf(name, sizeof(name), "D%u", i);
		sr_channel_new(sdi, i, SR_CHANNEL_LOGIC, TRUE, name);
	}

	devc = g_malloc0(sizeof(*devc));
	devc->cur_samplerate = RDC2_DEFAULT_SAMPLERATE;
	devc->limit_samples = 0;
	devc->data_source = RDC2_DATA_SOURCE_AUTO;
	devc->trigger_source = RDC2_TRIGGER_SOURCE_CH;
	devc->trigger_slope = RDC2_SLOPE_RISING;
	devc->state = RDC2_STATE_IDLE;
	sdi->priv = devc;

	return sdi;
}

static GSList *scan(struct sr_dev_driver *di, GSList *options)
{
	struct sr_config *src;
	struct sr_dev_inst *sdi;
	GSList *l, *ports, *devices;
	const char *conn, *serialcomm;

	conn = serialcomm = NULL;
	for (l = options; l; l = l->next) {
		src = l->data;
		switch (src->key) {
		case SR_CONF_CONN:
			conn = g_variant_get_string(src->data, NULL);
			break;
		case SR_CONF_SERIALCOMM:
			serialcomm = g_variant_get_string(src->data, NULL);
			break;
		}
	}
	if (!serialcomm)
		serialcomm = RDC2_SERIALCOMM;

	if (conn) {
		ports = g_slist_append(NULL, g_strdup(conn));
	} else {
		/*
		 * libserialport reports the OS name of the callout device
		 * (/dev/cu.* on macOS, /dev/ttyACM* on Linux, COM* on
		 * Windows), which is exactly what serial_open() expects.
		 */
		ports = sr_serial_find_usb(RDC2_USB_VID, RDC2_USB_PID);
	}

	devices = NULL;
	for (l = ports; l; l = l->next) {
		sdi = probe_port(l->data, serialcomm);
		if (sdi)
			devices = g_slist_append(devices, sdi);
	}
	g_slist_free_full(ports, g_free);

	return std_scan_complete(di, devices);
}

static int config_get(uint32_t key, GVariant **data,
	const struct sr_dev_inst *sdi, const struct sr_channel_group *cg)
{
	struct dev_context *devc;

	(void)cg;

	if (!sdi)
		return SR_ERR_ARG;
	devc = sdi->priv;

	switch (key) {
	case SR_CONF_CONN:
		if (!sdi->connection_id)
			return SR_ERR_NA;
		*data = g_variant_new_string(sdi->connection_id);
		break;
	case SR_CONF_SAMPLERATE:
		*data = g_variant_new_uint64(devc->cur_samplerate);
		break;
	case SR_CONF_LIMIT_SAMPLES:
		*data = g_variant_new_uint64(devc->limit_samples);
		break;
	case SR_CONF_DATA_SOURCE:
		*data = g_variant_new_string(data_sources[devc->data_source]);
		break;
	case SR_CONF_TRIGGER_SOURCE:
		*data = g_variant_new_string(
			trigger_sources[devc->trigger_source]);
		break;
	case SR_CONF_TRIGGER_SLOPE:
		*data = g_variant_new_string(
			trigger_slopes[devc->trigger_slope]);
		break;
	default:
		return SR_ERR_NA;
	}

	return SR_OK;
}

static int config_set(uint32_t key, GVariant *data,
	const struct sr_dev_inst *sdi, const struct sr_channel_group *cg)
{
	struct dev_context *devc;
	uint64_t samplerate;
	int idx;

	(void)cg;

	if (!sdi)
		return SR_ERR_ARG;
	devc = sdi->priv;

	switch (key) {
	case SR_CONF_SAMPLERATE:
		samplerate = g_variant_get_uint64(data);
		if (!rdc2_samplerate_find(samplerate)) {
			sr_err("Samplerate %" PRIu64 " is not supported.",
				samplerate);
			return SR_ERR_SAMPLERATE;
		}
		devc->cur_samplerate = samplerate;
		break;
	case SR_CONF_LIMIT_SAMPLES:
		devc->limit_samples = g_variant_get_uint64(data);
		break;
	case SR_CONF_DATA_SOURCE:
		idx = std_str_idx(data, ARRAY_AND_SIZE(data_sources));
		if (idx < 0)
			return SR_ERR_ARG;
		devc->data_source = idx;
		break;
	case SR_CONF_TRIGGER_SOURCE:
		idx = std_str_idx(data, ARRAY_AND_SIZE(trigger_sources));
		if (idx < 0)
			return SR_ERR_ARG;
		devc->trigger_source = idx;
		break;
	case SR_CONF_TRIGGER_SLOPE:
		idx = std_str_idx(data, ARRAY_AND_SIZE(trigger_slopes));
		if (idx < 0)
			return SR_ERR_ARG;
		devc->trigger_slope = idx;
		break;
	default:
		return SR_ERR_NA;
	}

	return SR_OK;
}

static int config_list(uint32_t key, GVariant **data,
	const struct sr_dev_inst *sdi, const struct sr_channel_group *cg)
{
	const uint64_t *samplerates;
	size_t num_samplerates;
	uint64_t min_samples, max_samples;

	switch (key) {
	case SR_CONF_SCAN_OPTIONS:
	case SR_CONF_DEVICE_OPTIONS:
		return STD_CONFIG_LIST(key, data, sdi, cg, scanopts, drvopts,
			devopts);
	case SR_CONF_SAMPLERATE:
		samplerates = rdc2_samplerate_list(sdi, &num_samplerates);
		*data = std_gvar_samplerates(samplerates, num_samplerates);
		break;
	case SR_CONF_LIMIT_SAMPLES:
		if (!sdi)
			return SR_ERR_ARG;
		rdc2_sample_limits(sdi, &min_samples, &max_samples);
		*data = std_gvar_tuple_u64(min_samples, max_samples);
		break;
	case SR_CONF_TRIGGER_MATCH:
		*data = std_gvar_array_i32(ARRAY_AND_SIZE(trigger_matches));
		break;
	case SR_CONF_DATA_SOURCE:
		*data = std_gvar_array_str(ARRAY_AND_SIZE(data_sources));
		break;
	case SR_CONF_TRIGGER_SOURCE:
		*data = std_gvar_array_str(ARRAY_AND_SIZE(trigger_sources));
		break;
	case SR_CONF_TRIGGER_SLOPE:
		*data = std_gvar_array_str(ARRAY_AND_SIZE(trigger_slopes));
		break;
	default:
		return SR_ERR_NA;
	}

	return SR_OK;
}

static int dev_acquisition_start(const struct sr_dev_inst *sdi)
{
	int ret;

	if ((ret = rdc2_setup_capture(sdi)) != SR_OK)
		return ret;

	return rdc2_start_acquisition(sdi);
}

static int dev_acquisition_stop(struct sr_dev_inst *sdi)
{
	return rdc2_stop_acquisition(sdi);
}

static struct sr_dev_driver chipdip_rdc2_0064_driver_info = {
	.name = "chipdip-rdc2-0064",
	.longname = "ChipDip RDC2-0064",
	.api_version = 1,
	.init = std_init,
	.cleanup = std_cleanup,
	.scan = scan,
	.dev_list = std_dev_list,
	.dev_clear = dev_clear,
	.config_get = config_get,
	.config_set = config_set,
	.config_list = config_list,
	.dev_open = std_serial_dev_open,
	.dev_close = std_serial_dev_close,
	.dev_acquisition_start = dev_acquisition_start,
	.dev_acquisition_stop = dev_acquisition_stop,
	.context = NULL,
};
SR_REGISTER_DEV_DRIVER(chipdip_rdc2_0064_driver_info);
