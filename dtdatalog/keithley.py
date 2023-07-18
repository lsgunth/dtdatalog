#!/usr/bin/env python3
##############################################################################
#
#   Filename: keithley.py
#
#   Author:   Ahmas El-Hamamsy <ahmase@deltatee.com>
#             Logan Gunthorpe <logang@deltatee.com>
#   Project:  Deltatee General
#
#   Description:
#        Contains the Keithley2700 and KeithleyError classes for interfacing
#        with a Keithley 2700 (including the 7700 Multiplexer). Running this
#        file as a standalone script will perform a communications test on the
#        specified com port.
#
#   (c) Deltatee Enterprises Ltd. 2013
#
##############################################################################

from . import datalog

import os
import sys
import time
import serial
import logging

from numpy.polynomial.polynomial import Polynomial

class KeithleyError(Exception):
    pass

logger = logging.getLogger(__name__)

THERMOCOUPLE_TABLES = {
	"K": [(0,  # -200 to 0 °C
           Polynomial((0.0000000E+00,
                       2.5173462E+01,
                      -1.1662878E+00,
                      -1.0833638E+00,
                      -8.9773540E-01,
                      -3.7342377E-01,
                      -8.6632643E-02,
                      -1.0450598E-02,
                      -5.1920577E-04))),
          (20.644, #0 to 500 °C
           Polynomial((0.000000E+00,
                       2.508355E+01,
                       7.860106E-02,
                      -2.503131E-01,
                       8.315270E-02,
                      -1.228034E-02,
                       9.804036E-04,
                      -4.413030E-05,
                       1.057734E-06,
                      -1.052755E-08))),
          (54.886, #500 to 1872 °C
           Polynomial((-1.318058E+02,
                       4.830222E+01,
                      -1.646031E+00,
                       5.464731E-02,
                      -9.650715E-04,
                       8.802193E-06,
                      -3.110810E-08))),
           ]
}

class Keithley2700(object):
    def __init__(self, port):
        try:
            self._serial = serial.Serial(port=port,
                                         baudrate=19200,
                                         timeout=2)
            self._serial.flush()
            self.reset()
            time.sleep(1)
        except serial.SerialException as e:
            raise KeithleyError("Could not connect to serial port {0}".format(port))

    def _command(self, cmd, error=True):
        logger.debug(cmd.strip())
        if error:
            self._serial.write(b"SYST:CLE\n")

        self._serial.write(cmd.encode("ASCII") + b"\n")

        if not error:
            return

        self._serial.write(b"SYST:ERR?\n")
        err = None
        while not err:
            err = self._serial.readline().decode("ASCII")
            logger.debug(err.strip())

        code, text = err.split(",")
        if int(code) != 0:
            text = text.strip().strip('"')
            raise KeithleyError(("Keithley reported an error while running " +
                                "\"{}\": {} ({})").format(cmd, text, code))

    def _query(self, cmd=None):
        if cmd: self._command(cmd, error=False)
        ret = None
        while not ret:
            ret = self._serial.readline().strip().decode("ASCII")
        logger.debug(ret)
        return ret

    def _reset(self):
        self._serial.write(b"\r\n\r\n")
        self._serial.flush()
        time.sleep(0.05)
        self._serial.reset_input_buffer()
        result = self._query("*IDN?")
        if not result.startswith("KEITHLEY"):
            raise KeithleyError("Failed to communicate with Keithley instrument.")

        self._command("*RST", error=False)
        self._command("SYST:BEEP off", error=False)
        self._command("ROUT:CLOSE:ACON 1", error=False)
        self._command("TRAC:CLEAR")

    def reset(self):
        self._reset()
        self._lastread = 0
        self._config = {}

    def setup_ch(self, func, channel=0, aper=None, range=None, **kws):
        clist = ""
        if channel >= 100:
            clist = ", (@{})".format(channel)

        if func == "RTD":
            func = "RES"
        elif func == "THERMOCOUPLE":
            func = "VOLT:DC"
            range = 0.1

        self._command("FUNC '{}'".format(func) + clist)

        if range is None:
            self._command("{}:RANG:AUTO ON".format(func) + clist)
        else:
            self._command("{}:RANG {}".format(func,range) + clist)

        if aper:
            self._command("{}:APER {}".format(func, aper) + clist)

    def add(self, func, channel=0, *args, **kws):
        if func not in ("VOLT:DC", "VOLT:AC" "CURR:DC", "CURR:AC", "RES",
                        "FRES", "TEMP", "FREQ", "PER", "CONT", "RTD",
                        "THERMOCOUPLE"):
            raise ValueError(f"Invalid function specified: {func}")

        self._config[channel] = func, args, kws
        self.setup_ch(func, channel, *args, **kws)

        return channel

    def remove(self, channel):
        if channel in self._config:
            del self._config[channel]

    def rtd_to_deg_c(self, ohms, alpha=0.00385, ro=1000, **kws):
        return (ohms / ro - 1) / alpha

    def thermocouple_to_deg_c(self, mv, sensor_type="K", **kws):
        if abs(mv) > 100:
            return None

        for mv_max, poly in THERMOCOUPLE_TABLES[sensor_type]:
            if mv >= mv_max:
                continue

            return poly(mv) + self.cold_junction_temp

    def read(self, channel):
        if channel not in self._config:
            raise KeithleyError("Unconfigured Channel: {0}.".format(channel))
        elif channel != self._lastread:
            func, args, kws = self._config[channel]
            if channel >= 100:
                self._command("ROUT:CLOS (@{0})".format(channel))
            else:
                self._command("ROUT:OPEN:ALL".format(channel))
                self.setup_ch(func, *args, **kws)

        ret = self._query("READ?").split(',')
        self._lastread = channel
        val = float(ret[0][:-3])

        if func == "RTD":
            rtd_val = self.rtd_to_deg_c(val, **kws)
            if kws.get("cold_junction", None):
                self.cold_junction_temp = rtd_val
            return rtd_val
        elif func == "THERMOCOUPLE":
            return self.thermocouple_to_deg_c(val, **kws)
        else:
            return val

    def readall(self):
        ret = {}
        channels = self._config.keys()
        for ch in channels:
            ret[ch] = self.read(ch)
        return ret

class Channel:
    def __init__(self, func, name, ch, **kws):
        self.name = name
        self.func = func
        self.channel = ch
        self.kws = kws

    def setup(self, keithley):
        return keithley.add(self.func, self.channel, **self.kws)

class RTD(Channel):
    def __init__(self, name, ch, alpha=0.00385, ro=1000, cold_junction=False, **kws):
        super().__init__("RTD", name, ch, alpha=alpha, ro=ro,
                         cold_junction=cold_junction, **kws)

class Thermocouple(Channel):
    def __init__(self, name, ch, sensor_type="K", **kws):
        super().__init__("THERMOCOUPLE", name, ch, sensor_type=sensor_type, **kws)

class KeithleyDataThread(datalog.DataThreadBase):
    connect_args = [{"opts": ("--keithley", "-K"),
                     "required": True,
                     "help": "Keithley Serial Port"}]
    channels = []
    name = "keithley"
    format = "{:>10.3f}"

    def __init__(self, *args, **kws):
        self.titles = [c.name for c in self.channels]
        super().__init__(*args, **kws)

    def connect(self, keithley, **kws):
        self.keithley = Keithley2700(keithley)

        self.chnums = []
        for c in self.channels:
            self.chnums.append(c.setup(self.keithley))

    def capture_sample(self):
        return (self.keithley.read(c) for c in self.chnums)

class ThermocoupleBlockDataThread(KeithleyDataThread):
    name = "thermoblock"
    channels = [
        RTD("RTD", 106, alpha=0.00385, ro=1000, cold_junction=True),
        Thermocouple("T12", 112, sensor_type="K"),
        Thermocouple("T13", 113, sensor_type="K"),
        Thermocouple("T14", 114, sensor_type="K"),
        Thermocouple("T15", 115, sensor_type="K"),
        Thermocouple("T16", 116, sensor_type="K"),
    ]

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--port",
                        help="keithley serial port")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="print keithley commands")
    options = parser.parse_args()

    if options.verbose:
        logging.basicConfig(level=logging.DEBUG)

    try:
        k = Keithley2700(options.port)

        rtd = k.add("RES", 106)
        print(k.read(rtd))
        print(k.read(rtd))
        print(k.read(rtd))

    except (KeithleyError, serial.SerialException) as e:
        print(e)
    except KeyboardInterrupt:
        pass
