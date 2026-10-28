"""Archive tools: extract and create zip/tar."""

import fnmatch
import gzip
import os
import shutil
import sys
import tarfile
import zipfile
from pathlib import Path

from axion.security import fs_path, inside
from axion.state import ask, ToolError, track
from axion.tools.files import trash_item
from axion.tools.registry import B, L, S, tool
from axion.ui import acc, dim, IS_TTY
from axion.util import denied, human_size, rel


def progress(label, i, n):
    if IS_TTY:
        sys.stdout.write("\r\033[K  " + acc("⠿") + " " + dim("%s %d/%d" % (label, i, n)))
        sys.stdout.flush()


def progress_done():
    if IS_TTY:
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()


def strip_archive_ext(name):
    for ext in (".tar.gz", ".tar.bz2", ".tar.xz", ".tgz", ".tbz2", ".txz", ".zip", ".tar", ".gz"):
        if name.lower().endswith(ext):
            return name[: -len(ext)] or name
    return name


def archive_members(arc, password=None):
    """Return (kind, [(name, size, is_dir)])"""
    low = arc.name.lower()
    if low.endswith(".zip") or zipfile.is_zipfile(str(arc)):
        with zipfile.ZipFile(str(arc)) as z:
            return "zip", [(i.filename, i.file_size, i.is_dir()) for i in z.infolist()]
    if tarfile.is_tarfile(str(arc)):
        with tarfile.open(str(arc)) as t:
            return "tar", [(m.name, m.size, m.isdir()) for m in t.getmembers()]
    if low.endswith(".gz"):
        return "gz", [(arc.name[:-3], arc.stat().st_size, False)]
    raise ToolError("unsupported archive format (%s). For .7z/.rar: pkg install p7zip, then run_shell '7z x file'." % arc.suffix)


@tool("extract_archive", "Extract a zip / tar / tar.gz / tgz / tar.bz2 / tar.xz / gz archive. list_only=true lists the contents without extracting. Default destination: a folder named after the archive, next to it.",
      {"path": S("archive path"), "dest": S("destination folder (optional)"), "list_only": B("list contents only"),
       "overwrite": B("overwrite existing files (default: skip them)"), "password": S("zip password (optional)")},
      ["path"])
def t_extract_archive(a, ctx):
    arc = fs_path(ctx, a.get("path"), "extracting an archive (source)")
    if not arc.is_file():
        raise ToolError("archive not found: %s" % a.get("path"))
    try:
        kind, members = archive_members(arc)
    except (zipfile.BadZipFile, tarfile.TarError, OSError) as e:
        raise ToolError("archive is corrupt or unreadable: %s" % e)
    nfiles = sum(1 for m in members if not m[2])
    total = sum(m[1] for m in members)
    if a.get("list_only"):
        lines = ["%s  (%s)" % (m[0], "folder" if m[2] else human_size(m[1])) for m in members[:200]]
        more = "\n… +%d more" % (len(members) - 200) if len(members) > 200 else ""
        return "[%s · %d file · %s]\n%s%s" % (arc.name, nfiles, human_size(total), "\n".join(lines), more)
    dest = fs_path(ctx, a.get("dest") or (arc.parent / strip_archive_ext(arc.name)), "extracting to", write=True)
    existed = dest.exists()
    overwrite = bool(a.get("overwrite"))
    det = ["%d files · %s after extraction" % (nfiles, human_size(total))]
    if existed:
        det.append("destination folder already exists: files with the same name will be %s" % ("OVERWRITTEN" if overwrite else "skipped"))
    okk, why = ask(ctx, "Extract", "%s  →  %s" % (rel(ctx, arc), rel(ctx, dest)), det)
    if not okk:
        return denied(why)
    dest.mkdir(parents=True, exist_ok=True)
    droot = Path(os.path.realpath(str(dest)))
    created, skipped, done = [], 0, 0
    pw = a.get("password")
    try:
        if kind == "zip":
            with zipfile.ZipFile(str(arc)) as z:
                if pw:
                    z.setpassword(str(pw).encode())
                infos = z.infolist()
                for idx, info in enumerate(infos, 1):
                    target = Path(os.path.realpath(str(droot / info.filename)))
                    if not inside(target, droot):
                        raise ToolError("unsafe entry rejected (path traversal): %s" % info.filename)
                    if info.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    if target.exists() and not overwrite:
                        skipped += 1
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(info) as src_f, open(str(target), "wb") as dst_f:
                        shutil.copyfileobj(src_f, dst_f)
                    created.append(target)
                    done += 1
                    if idx % 10 == 0:
                        progress("extracting", idx, len(infos))
        elif kind == "tar":
            with tarfile.open(str(arc)) as t:
                ms = t.getmembers()
                for idx, m in enumerate(ms, 1):
                    target = Path(os.path.realpath(str(droot / m.name)))
                    if not inside(target, droot):
                        raise ToolError("unsafe entry rejected (path traversal): %s" % m.name)
                    if m.isdir():
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    if not m.isfile():
                        skipped += 1
                        continue
                    if target.exists() and not overwrite:
                        skipped += 1
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    f = t.extractfile(m)
                    if f is None:
                        continue
                    with f, open(str(target), "wb") as dst_f:
                        shutil.copyfileobj(f, dst_f)
                    created.append(target)
                    done += 1
                    if idx % 10 == 0:
                        progress("extracting", idx, len(ms))
        else:  # single gz file
            target = droot / members[0][0]
            if target.exists() and not overwrite:
                skipped += 1
            else:
                with gzip.open(str(arc), "rb") as f, open(str(target), "wb") as dst_f:
                    shutil.copyfileobj(f, dst_f)
                created.append(target)
                done += 1
    except RuntimeError as e:
        progress_done()
        raise ToolError("extraction failed (encrypted zip? provide a password): %s" % e)
    except (zipfile.BadZipFile, tarfile.TarError, OSError, EOFError) as e:
        progress_done()
        raise ToolError("extraction failed: %s" % e)
    progress_done()
    ctx.undo.append({"t": "extract", "dest": dest, "new_dir": not existed, "created": created[:5000]})
    track(ctx, "+", dest, "%d file" % done)
    return "OK: %d files extracted to %s%s" % (done, rel(ctx, dest), (" (%d skipped)" % skipped) if skipped else "")


def path_excluded(rel_path, name, patterns):
    for pat in patterns:
        pat = str(pat).strip()
        if not pat:
            continue
        if fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(rel_path, pat) or fnmatch.fnmatch("/" + rel_path, pat):
            return True
        if any(fnmatch.fnmatch(part, pat) for part in rel_path.split("/")):
            return True
    return False


@tool("create_archive", "Create a zip or tar.gz archive from files or folders. The format follows the output extension. Use exclude to drop junk (node_modules, .git, build, *.bak, ...). The archive never contains itself.",
      {"output": S("archive path, e.g. project1.zip"), "paths": L("source files/folders, default ['.']"),
       "exclude": L("patterns to exclude, e.g. ['*.zip','node_modules','.git']"),
       "format": S("zip or tar.gz (optional)")}, ["output"])
def t_create_archive(a, ctx):
    outp = fs_path(ctx, a.get("output"), "creating an archive", write=True)
    srcs = [fs_path(ctx, p, "archiving (source)") for p in (a.get("paths") or ["."])]
    excludes = list(a.get("exclude") or [])
    fmt = str(a.get("format") or ("tar.gz" if outp.name.lower().endswith((".tar.gz", ".tgz")) else "zip")).lower()
    if fmt not in ("zip", "tar.gz"):
        raise ToolError("format must be zip or tar.gz")
    entries, total = [], 0
    for src in srcs:
        if not src.exists():
            raise ToolError("source not found: %s" % src)
        if src.is_file():
            if src != outp:
                entries.append((src, src.name))
            continue
        base = src if len(srcs) == 1 else src.parent
        for dp, dns, fns in os.walk(str(src)):
            rdp = os.path.relpath(dp, str(base))
            dns[:] = [d for d in dns if not path_excluded(os.path.normpath(os.path.join(rdp, d)).replace("\\", "/").lstrip("./") or d, d, excludes)]
            for fn in fns:
                fp = Path(dp) / fn
                if fp == outp or fp.is_symlink():
                    continue
                arc = os.path.normpath(os.path.join(rdp, fn)).replace("\\", "/")
                arc = arc[2:] if arc.startswith("./") else arc
                if path_excluded(arc, fn, excludes):
                    continue
                entries.append((fp, arc))
    for fp, _ in entries:
        try:
            total += fp.stat().st_size
        except OSError:
            pass
    if not entries:
        raise ToolError("no files to archive (check exclude)")
    det = ["%d file · %s" % (len(entries), human_size(total)), "format: %s" % fmt]
    if excludes:
        det.append("except: " + ", ".join(map(str, excludes))[:120])
    if outp.exists():
        det.append("the existing archive will be overwritten")
    okk, why = ask(ctx, "Archive", rel(ctx, outp), det)
    if not okk:
        return denied(why)
    outp.parent.mkdir(parents=True, exist_ok=True)
    old_exists = outp.exists()
    if old_exists:
        trash_item(outp)
    try:
        if fmt == "zip":
            with zipfile.ZipFile(str(outp), "w", zipfile.ZIP_DEFLATED) as z:
                for i, (fp, arc) in enumerate(entries, 1):
                    z.write(str(fp), arc)
                    if i % 20 == 0:
                        progress("archiving", i, len(entries))
        else:
            with tarfile.open(str(outp), "w:gz") as t:
                for i, (fp, arc) in enumerate(entries, 1):
                    t.add(str(fp), arcname=arc, recursive=False)
                    if i % 20 == 0:
                        progress("archiving", i, len(entries))
    except OSError as e:
        progress_done()
        raise ToolError("could not create the archive: %s" % e)
    progress_done()
    size = outp.stat().st_size
    ctx.undo.append({"t": "copy", "dst": outp})
    track(ctx, "+", outp, human_size(size))
    return "OK: %s created · %d files · %s (from %s)" % (rel(ctx, outp), len(entries), human_size(size), human_size(total))
