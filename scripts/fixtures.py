import uuid
import zipfile

from unified_re.common import ROOT


def archive_fixture():
    directory = ROOT / "var/fixtures"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ("owned-archive-" + uuid.uuid4().hex + ".zip")
    with zipfile.ZipFile(path, "x") as archive:
        for name in ("package.json", "main.js", "helper.js"):
            archive.writestr(name, (ROOT / "samples/demo-app" / name).read_bytes())
    return path
