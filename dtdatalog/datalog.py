
import collections
import pathlib
import threading
import time

class FileWriter:
    metadata = collections.OrderedDict()
    metadata['Timestamp'] = time.asctime()
    fname_suffix = None
    title_format = "{:>10}"
    time_format = "{:>10.4f}"
    format = "{:>10}"

    def __init__(self, fname=None, metadata={}, *args, **kws):
        super().__init__(*args, **kws)
        self.metadata.update(metadata)

        if fname is None:
            fname = ""

        if fname:
            fname += "_"

        if self.fname_suffix:
            suffix = self.fname_suffix
        else:
            suffix = getattr(self, "name", "")

        if suffix:
            suffix = "_" + suffix

        idx = 0
        while True:
            self.name = pathlib.Path(f"{fname}{idx:03}{suffix}.dat")
            if not self.name.exists():
                break
            idx += 1

        print(f"Saving data to {self.name}")
        self.f = open(self.name, "w")
        self.write_header()

    def write_header(self):
        for k, v in self.metadata.items():
            self.f.write("# {}: {}\n".format(k, v))

        titles = ["TIME"] + self.titles
        self.title_fmt = " ".join([self.title_format] * len(titles)) + "\n"
        self.line_fmt = " ".join([self.format] * len(self.titles)) + "\n"
        self.line_fmt = self.time_format + " " + self.line_fmt
        title_line = self.title_fmt.format(*titles)
        self.f.write(title_line)

    def output_data(self, values):
        self.f.write(self.line_fmt.format(*values))
        self.f.flush()

class DataThreadBase(FileWriter, threading.Thread):
    connect_args = {}
    name = "data"

    def __init__(self, start_time=None, *args, **kws):
        if start_time is None:
            self.start_time = time.time()
        else:
            self.start_time = start_time

        self.stopping = threading.Event()
        super().__init__(*args, **kws)

    def connect(self):
        pass

    def stop(self):
        self.stopping.set()
        return self.join()

    def __enter__(self):
        self.start()

    def __exit__(self, typ, value, traceback):
        self.stop()

    def run(self):
        while not self.stopping.is_set():
            tm = time.time() - self.start_time
            sample = self.capture_sample()
            self.output_data((tm, ) + tuple(sample))
