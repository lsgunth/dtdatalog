
import argparse
import contextlib
import time

class Program:
    def __init__(self, data_sources, plot_types,
                 prog="Data Logger", description=None):
        self.parser = argparse.ArgumentParser(prog, description)

        for d in data_sources:
            for c in d.connect_args:
                opts = c.pop("opts")
                self.parser.add_argument(*opts, **c)

        self.data_sources = data_sources

    def run(self):
        try:
            args = self.parser.parse_args()

            for ds in self.data_sources:
                ds.connect(**vars(args))

            with contextlib.ExitStack() as s:
                for ds in self.data_sources:
                    s.enter_context(ds)

                while True:
                    time.sleep(60)

        except KeyboardInterrupt:
            print()
