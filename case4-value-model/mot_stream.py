"""Read the UK DVSA anonymised MOT extracts over HTTP, without downloading a year.

The results files are 4.5 GB zipped per release and the machine has about 4 GB free, so nothing
here is ever saved. `RemoteZipFile` serves byte ranges to Python's own `zipfile`, which then
handles stored, deflate and deflate64 members alike; callers pull rows and throw them away.

The one fact the whole readiness engine rests on is that `vehicle_id` identifies the same car
across releases. DVSA's user guide says so - "Unique vehicles can be tracked using the Vehicle ID
field, which is based upon the Registration and VIN" (mot-testing-data-user-guide-v5.1.odt) - and
`check_vehicle_id()` below tests it against the data instead of taking their word for it.

Source: https://open.data.dvsa.gov.uk/mot-anonymised/  Open Government Licence v3.0.

Usage: .venv/bin/python mot_stream.py          # runs the vehicle_id check and prints the table
"""
import io
import zipfile
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import zipfile_deflate64  # noqa: F401  - registers deflate64 (method 9) with zipfile

BUCKET = "https://edh-dvsa-data-gov-uk-files-prod.s3.eu-west-1.amazonaws.com/"

# Which archive holds which test year. The 2024 and 2025 releases split the year into stored
# monthly members, so any month can be read on its own. 2022 and 2023 are one deflate64 member
# each, which can only be read from the start.
ARCHIVES = {
    2025: "dft_test_result_extracts_2025.zip",
    2024: "dft_test_result_extracts_2024.zip",
    2023: "dft_test_result_2023.zip",
    2022: "dft_test_result_2022.zip",
    # The May 2025 release of test year 2024, kept because it is a second, independent build of
    # the same tests and so is what makes the cross-release check possible.
    "2024_may2025": "MOT+testing+data+results+(2024).zip",
}

COLUMNS = ["test_id", "vehicle_id", "test_date", "test_class_id", "test_type", "test_result",
           "test_mileage", "postcode_area", "make", "model", "colour", "fuel_type",
           "cylinder_capacity", "first_use_date", "completed_date"]
IDX = {name: i for i, name in enumerate(COLUMNS)}
CARS = "4"          # test class 4 is cars and light vans
NORMAL_TEST = "NT"  # not a retest


class RemoteFile(io.RawIOBase):
    """A seekable read-only file over HTTP, for `zipfile` to work against.

    Reading a 4.5 GB archive is almost all sequential, so this holds **one open streaming
    response** and reads from it, rather than issuing a range request per block. That matters more
    than it sounds: a fresh request per block is a fresh TCP and TLS handshake to S3, and on a
    domestic line it costs three to five times the throughput. A seek outside the open stream -
    which `zipfile` does once per member, to read its header - reopens it.
    """

    def __init__(self, url, block=1 << 23):
        self.url = url
        self.block = block
        self.pos = 0
        self.bytes_fetched = 0
        self._stream = None
        self._stream_pos = None
        self._cache = (0, b"")
        with urlopen(Request(url, method="HEAD"), timeout=60) as r:
            self.size = int(r.headers["Content-Length"])

    def _open_stream(self, start):
        self._close_stream()
        req = Request(self.url, headers={"Range": f"bytes={start}-{self.size - 1}"})
        for attempt in range(4):
            try:
                self._stream = urlopen(req, timeout=300)
                break
            except (HTTPError, OSError):
                if attempt == 3:
                    raise
        self._stream_pos = start

    def _close_stream(self):
        if self._stream is not None:
            try:
                self._stream.close()
            except OSError:
                pass
        self._stream = None
        self._stream_pos = None

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.size - self.pos
        n = min(n, self.size - self.pos)
        if n <= 0:
            return b""
        start, buf = self._cache
        if start <= self.pos and self.pos + n <= start + len(buf):
            off = self.pos - start
            self.pos += n
            return buf[off:off + n]
        if self._stream is None or self._stream_pos != self.pos:
            self._open_stream(self.pos)
        want = min(max(n, self.block), self.size - self.pos)
        chunks, got = [], 0
        while got < want:
            piece = self._stream.read(want - got)
            if not piece:
                break
            chunks.append(piece)
            got += len(piece)
        buf = b"".join(chunks)
        self.bytes_fetched += len(buf)
        self._stream_pos = self.pos + len(buf)
        self._cache = (self.pos, buf)
        out = buf[:n]
        self.pos += len(out)
        return out

    def readinto(self, b):
        data = self.read(len(b))
        b[:len(data)] = data
        return len(data)

    def seek(self, offset, whence=io.SEEK_SET):
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self.pos, io.SEEK_END: self.size}[whence]
        self.pos = max(0, min(self.size, base + offset))
        return self.pos

    def tell(self):
        return self.pos

    def seekable(self):
        return True

    def readable(self):
        return True


def archive(year):
    """The zip for a test year, opened over the network."""
    return zipfile.ZipFile(RemoteFile(BUCKET + ARCHIVES[year]))


def members(year, month=None):
    """Member names for a test year, newest release first, skipping macOS resource forks."""
    zf = archive(year)
    names = [n for n in zf.namelist()
             if n.endswith(".csv") and not n.startswith("__MACOSX")]
    if month is not None:
        tag = f"{str(year)[:4]}{month:02d}"
        names = [n for n in names if tag in n]
    return zf, sorted(names)


def _layout(header):
    """Releases differ. 2024 and 2025 are comma-separated with a completed_date; 2022 and 2023
    are pipe-separated without one. Read the header rather than assume either."""
    sep = b"|" if header.count(b"|") > header.count(b",") else b","
    names = header.rstrip(b"\r").decode().split(sep.decode())
    if names != COLUMNS[:len(names)]:
        raise ValueError(f"unexpected MOT columns: {names}")
    return sep, len(names)


def rows(zf, name, max_bytes=None, cars_only=True, normal_only=True):
    """Yield parsed rows of one member, always in the 15-column order of `COLUMNS`.

    Stops after `max_bytes` of the decompressed file. Rows with the wrong field count are
    skipped: a handful of model names carry the separator.
    """
    read = 0
    tail = b""
    sep = None
    want = None
    # a cheap substring test that throws most rows away before the split
    quick = None
    with zf.open(name) as fh:
        while True:
            chunk = fh.read(1 << 22)
            if not chunk:
                break
            read += len(chunk)
            lines = (tail + chunk).split(b"\n")
            tail = lines.pop()
            if sep is None:
                sep, want = _layout(lines[0])
                lines = lines[1:]
                if cars_only and normal_only:
                    quick = sep + CARS.encode() + sep + NORMAL_TEST.encode() + sep
            for line in lines:
                if quick is not None and quick not in line:
                    continue
                parts = line.rstrip(b"\r").decode("utf-8", "replace").split(sep.decode())
                if len(parts) != want:
                    continue
                if cars_only and parts[3] != CARS:
                    continue
                if normal_only and parts[4] != NORMAL_TEST:
                    continue
                yield parts + [""] * (len(COLUMNS) - want)
            if max_bytes and read >= max_bytes:
                return


def vehicle_ids(zf, name):
    """Just the vehicle ids of a member, as ints. Splitting only the first two fields is several
    times faster than parsing the row, and a follow-up pass needs nothing else."""
    tail = b""
    sep = None
    with zf.open(name) as fh:
        while True:
            chunk = fh.read(1 << 22)
            if not chunk:
                break
            lines = (tail + chunk).split(b"\n")
            tail = lines.pop()
            if sep is None:
                sep, _ = _layout(lines[0])
                lines = lines[1:]
            for line in lines:
                bits = line.split(sep, 2)
                if len(bits) == 3:
                    try:
                        yield int(bits[1])
                    except ValueError:
                        pass


def mileage(parts):
    """Odometer in miles, or None. Zero or blank means no reading was taken."""
    try:
        m = int(float(parts[IDX["test_mileage"]]))
    except ValueError:
        return None
    return m if m > 0 else None


def reg_year(parts):
    """Year of first use, or None."""
    try:
        return int(parts[IDX["first_use_date"]][:4])
    except ValueError:
        return None


# ---------- the check the engine rests on ----------

def check_vehicle_id(sample_bytes=90 << 20, follow_bytes=(200 << 20, 120 << 20)):
    """Does `vehicle_id` mean the same car across releases? Two tests and a null.

    1. Test year 2024 exists in two releases built thirteen months apart. Join them on `test_id`
       and ask whether `vehicle_id` agrees.
    2. Take January 2024 cars and look for them a year later. If the id travels, make, model and
       first-use date must agree and the odometer must not have gone backwards.

    The null is the chance that two unrelated cars agree anyway, computed from the sample's own
    make, model and first-use-date distributions.
    """
    out = {}

    zf_new, [name_new] = members(2024, month=1)
    a = {}
    for p in rows(zf_new, name_new, max_bytes=sample_bytes, cars_only=False, normal_only=False):
        a[p[0]] = p
    zf_old, [name_old] = members("2024_may2025", month=1)
    b = {}
    for p in rows(zf_old, name_old, max_bytes=sample_bytes + (60 << 20),
                  cars_only=False, normal_only=False):
        b[p[0]] = p
    both = set(a) & set(b)
    out["cross_release_tests"] = len(both)
    out["cross_release_same_vehicle_id"] = sum(1 for t in both if a[t][1] == b[t][1]) / len(both)

    base, makes, fuds, n = {}, {}, {}, 0
    for p in rows(zf_new, name_new, max_bytes=sample_bytes):
        m = mileage(p)
        if m is None:
            continue
        base[int(p[1])] = (m, p[8], p[9], p[13], p[2])
        n += 1
        key = (p[8], p[9])
        makes[key] = makes.get(key, 0) + 1
        fuds[p[13]] = fuds.get(p[13], 0) + 1
    out["base_cars"] = n
    out["chance_make_model"] = sum((v / n) ** 2 for v in makes.values())
    out["chance_first_use"] = sum((v / n) ** 2 for v in fuds.values())

    hit = attr = fud = risen = 0
    zf25, _ = members(2025, month=1)
    for month, budget in zip((1, 2), follow_bytes):
        _, [name] = members(2025, month=month)
        for p in rows(zf25, name, max_bytes=budget):
            prev = base.get(int(p[1]))
            if prev is None:
                continue
            hit += 1
            attr += (prev[1] == p[8] and prev[2] == p[9])
            fud += (prev[3] == p[13])
            m = mileage(p)
            risen += (m is not None and m >= prev[0])
    out["followed"] = hit
    out["make_model_agree"] = attr / hit
    out["first_use_agree"] = fud / hit
    out["odometer_not_lower"] = risen / hit
    return out


if __name__ == "__main__":
    r = check_vehicle_id()
    print(f"cross-release: {r['cross_release_tests']:,} tests in both the May 2025 and the "
          f"June 2026 release of test year 2024")
    print(f"  vehicle_id identical      {r['cross_release_same_vehicle_id']:.4f}")
    print(f"across years: {r['base_cars']:,} January 2024 cars, {r['followed']:,} found again")
    print(f"  make and model agree      {r['make_model_agree']:.4f} "
          f"(by chance {r['chance_make_model']:.4f})")
    print(f"  first use date agrees     {r['first_use_agree']:.4f} "
          f"(by chance {r['chance_first_use']:.4f})")
    print(f"  odometer not lower        {r['odometer_not_lower']:.4f}")
