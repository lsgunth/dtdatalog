#!/usr/bin/env python3

from dtdatalog import Program, keithley

if __name__ == "__main__":
    p = Program([keithley.ThermocoupleBlockDataThread()],
                [])
    p.run()
