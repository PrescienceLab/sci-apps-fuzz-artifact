# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "matplotlib>=3.10.8",
#     "numpy>=2.4.2",
# ]
# ///
import argparse
import json
import os
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter

matplotlib.rcParams["pdf.fonttype"] = 42


class LazyJsonData:
    _cache = {}

    def __init__(self, relative_path: str):
        script_dir = Path(__file__).resolve().parent
        self._path = (script_dir / relative_path).resolve()

    def _load(self):
        if self._path not in self._cache:
            with self._path.open("r", encoding="utf-8") as f:
                self._cache[self._path] = json.load(f)

    @property
    def data(self):
        self._load()
        return self._cache[self._path]

    def __getitem__(self, key):
        self._load()
        return self._cache[self._path][key]

    def get(self, key, default=None):
        self._load()
        return self._cache[self._path].get(key, default)


def assign_colors(labels):
    return {
        s: plt.get_cmap("gist_rainbow")(i / len(labels)) for i, s in enumerate(labels)
    }


def is_nonneg_integer(value):
    try:
        v = int(value)
        return v >= 0
    except (ValueError, TypeError):
        return False


def to_minutes(milliseconds):
    return milliseconds / 1000 / 60


def to_days(milliseconds):
    return to_minutes(milliseconds) / 60 / 24


applications_pretty_print = {
    "enzo": "Enzo",
    "gromacs": "GROMACS",
    "laghos": "Laghos",
    "lammps": "LAMMPS",
}

applications_debug_use_relative_filenames = {
    "enzo": True,
    "gromacs": False,
    "laghos": True,
    "lammps": False,
}

exploitable_rule_shorts = [
    "ReturnAv",
    "UseAfterFree",
    "SegFaultOnPc",
    "BranchAv",
    "StackCodeExecution",
    "StackBufferOverflow",
    "PossibleStackCorruption",
    "DestAv",
    "BadInstruction",
    "HeapError",
    "StackOverflow",
    "SegFaultOnPcNearNull",
    "BranchAvNearNull",
    "BlockMoveAv",
    "DestAvNearNull",
    "SourceAvNearNull",
    "FloatingPointException",
    "BenignSignal",
    "SourceAv",
    "AbortSignal",
    "AccessViolation",
    "UncategorizedSignal",
    "(failed)",
]

exploitable_rule_colors = assign_colors(exploitable_rule_shorts)

exploitable_verdicts = [
    "Unclassified (failed)",
    "Not Exploitable",
    "Probably Not Exploitable",
    "Unknown",
    "ASAN-Triaged",
    "Probably Exploitable",
    "Exploitable",
]

exploitable_verdict_colors = {
    "Unclassified (failed)": "dodgerblue",
    "Not Exploitable": "green",
    "Probably Not Exploitable": "lime",
    "Unknown": "gold",
    "ASAN-Triaged": "orange",
    "Probably Exploitable": "salmon",
    "Exploitable": "red",
}

crashes_over_time_series = [
    "Total",
    "Likely Exploitable",
    "Exploitability Unknown",
]

crashes_over_time_colors = {
    "Total": "black",
    "Likely Exploitable": exploitable_verdict_colors["Exploitable"],
    "Exploitability Unknown": exploitable_verdict_colors["Unknown"],
}

crashes_over_time_linestyles = {
    "Total": "solid",
    "Likely Exploitable": "dotted",
    "Exploitability Unknown": "dashed",
}

SMALL_FIGURE_SIZE = (4.8, 2.85)

HATCHES = [
    "/",
    "\\",
    "|",
    "x",
    "//",
    "\\\\",
    "||",
    "xx",
    ".",
    "o",
    "O",
    "..",
    "**",
    "OO",
    "xx",
    "oo",
]


def asan_unslug(slug):
    return slug.replace("-", " ").lower().title()


asan_errors = [
    asan_unslug(s)
    for s in [
        "heap-use-after-free",
        "double-free",
        # "alloc-dealloc-mismatch",
        "heap-buffer-overflow",
        "stack-buffer-overflow",
        # "stack-buffer-underflow",
        "global-buffer-overflow",
        "stack-use-after-return",
        "stack-use-after-scope",
        # "initialization-order-fiasco",
        # "memory-leak",
        # "calloc-overflow",
        # "realloc-overflow",
        # "invalid-allocation-alignment",
        # "container-overflow",
        # "use-after-poison",
        "new-delete-type-mismatch",
        "out-of-memory",
        "unknown-crash",
        "invalid-pointer-free",
    ]
]

asan_colors = assign_colors(asan_errors)


def assoc_list_for(labels, assoc, kind="color"):
    if assoc is None:
        return None
    if not all(label in assoc for label in labels):
        missing = [label for label in labels if label not in assoc]
        raise ValueError(f"Missing {kind} assignments for labels: {missing}")
    return [assoc[label] for label in labels]


def color_list_for(labels, color_assoc):
    return assoc_list_for(labels, color_assoc, kind="color")


def parse_afl_input_name(name: str):
    # like 'fuzzer30:id:000005,sig:11,src:000000,time:198948,execs:3050,op:havoc,rep:14'
    tags = {}
    split_name = name.split(",")
    for s in split_name[1:]:
        if s.startswith("+"):
            continue
        s_split = s.split(":")
        tags[s_split[0]] = s_split[1]
    return tags


def fuzzer_run_name(orig_filename: str):
    for component in Path(orig_filename).parts:
        m = re.fullmatch(r"fuzzer-[^-]+-(.+)", component)
        if m is not None:
            return m.group(1)
    return None


def parse_fuzzer_run_names(spec: str):
    run_names = {}
    for entry in spec.split(","):
        entry = entry.strip()
        if entry == "":
            continue
        application, separator, run_name = entry.partition(":")
        if separator == "":
            application, run_name = None, entry
        else:
            application, run_name = application.strip(), run_name.strip()
        if run_name == "":
            raise argparse.ArgumentTypeError(f"{entry!r} does not name a fuzzer run")
        if application == "":
            raise argparse.ArgumentTypeError(f"{entry!r} does not name an application")
        if application in run_names:
            raise argparse.ArgumentTypeError(
                f"{entry!r} is a second run name for "
                + (f"application {application}" if application else "all applications")
            )
        run_names[application] = run_name
    if len(run_names) == 0:
        raise argparse.ArgumentTypeError("no fuzzer run names given")
    return run_names


def select_fuzzer_run(cw_data, run_name):
    if run_name is None:
        return cw_data

    selected = [
        d for d in cw_data if fuzzer_run_name(d["entry"]["orig_filename"]) == run_name
    ]
    if len(selected) == 0:
        available = sorted(
            {
                name
                for name in map(
                    lambda d: fuzzer_run_name(d["entry"]["orig_filename"]), cw_data
                )
                if name is not None
            }
        )
        print(
            f"WARNING: no crashes from fuzzer run {run_name!r}; "
            f"runs present in this data: {', '.join(available) or '(none)'}"
        )
    else:
        print(
            f"fuzzer run {run_name!r}: using {len(selected)} of {len(cw_data)} crashes"
        )
    return selected


def crash_time(cw_datum):
    time = cw_datum.get("time")
    if time is None or not is_nonneg_integer(time):
        return None
    return int(time)


def select_timed_crashes(cw_data):
    selected = [d for d in cw_data if crash_time(d) is not None]
    dropped = len(cw_data) - len(selected)
    if dropped != 0:
        print(
            f"WARNING: {dropped} of {len(cw_data)} crashes carry no time and are "
            f"left out of the crashes-over-time plot"
        )
    return selected


def format_metric_suffix(value, _position=None):
    for threshold, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if abs(value) >= threshold:
            return f"{value / threshold:g}{suffix}"
    return f"{value:g}"


def count_distinct_values(dict_list, key_lambda):
    values = [key_lambda(d) for d in dict_list]
    value_counts = Counter(values)
    return value_counts


def create_stacked_bar_chart_all(
    per_app_labeled_counter,
    filename,
    title=None,
    x_label=None,
    y_label=None,
    label_order=None,
    colors=None,
    small=False,
    legend_loc="upper left",
):
    applications = list(per_app_labeled_counter.keys())

    labels = list(dict.fromkeys(k for v in per_app_labeled_counter.values() for k in v))
    labels = list(dict.fromkeys(lab for lab in labels if lab is not None))

    value_counts = {
        label: np.array(
            [per_app_labeled_counter[a].get(label) or 0 for a in applications]
        )
        for label in labels
    }

    if label_order is None:
        label_order = sorted(
            labels, key=lambda label: sum(value_counts[label]), reverse=True
        )
    else:
        label_order = [lab for lab in label_order if lab in labels]
        for label in label_order:
            labels.remove(label)
        assert len(labels) == 0

    if small:
        figsize = SMALL_FIGURE_SIZE
    else:
        figsize = (5.8, 3.65)
    fig, ax = plt.subplots(figsize=figsize, layout="constrained")

    if not all(a in applications_pretty_print for a in applications):
        print("WARNING: no pretty-print name for some applications")
    applications = [applications_pretty_print.get(a) or a for a in applications]

    bottom = np.zeros(len(applications))
    hatch_idx = 0
    if len(label_order) > len(HATCHES):
        print(
            f"have {len(label_order)} labels but only {len(HATCHES)} hatches, add more"
        )
        exit(1)
    for label in label_order:
        counter_value = value_counts[label]
        print(applications, counter_value, label, bottom)
        hatch = HATCHES[hatch_idx]
        if colors is not None:
            bars = ax.bar(
                applications,
                counter_value,
                label=label,
                bottom=bottom,
                color=colors[label],
                hatch=hatch,
            )
        else:
            bars = ax.bar(
                applications, counter_value, label=label, bottom=bottom, hatch=hatch
            )

        if label == "ASAN-triaged":
            i = len(applications) - 1
            bar = bars[i]
            x_tip = bar.get_x() + bar.get_width()
            y_tip = bottom[i] + counter_value[i] / 2

            ax.annotate(
                "",
                xy=(1.02, y_tip),
                xycoords=("axes fraction", "data"),
                xytext=(x_tip, y_tip),
                textcoords="data",
                arrowprops=dict(
                    arrowstyle="->",
                    lw=3,
                    color=colors[label],
                    shrinkA=0,
                    shrinkB=0,
                    mutation_scale=18,
                ),
            )

        bottom += counter_value
        hatch_idx += 1

    if "outside" in legend_loc:
        legend = fig.legend(loc=legend_loc, reverse=True)
    else:
        legend = ax.legend(loc=legend_loc, reverse=True)

    labels_to_bold = [
        "Heap Buffer Overflow",
        "Invalid Pointer Free",
        "Stack Buffer Overflow",
        "Global Buffer Overflow",
        "Heap Use After Free",
        "Double Free",
        "Exploitable",
        "Probably Exploitable",
        "ASAN-Triaged",
    ]

    for text in legend.get_texts():
        if text.get_text() in labels_to_bold:
            text.set_fontweight("bold")

    if title:
        ax.set_title(title)
    if x_label:
        ax.set_xlabel(x_label)
    if y_label:
        ax.set_ylabel(y_label)

    fig.savefig(
        filename, bbox_inches="tight", format="pdf", metadata={"CreationDate": None}
    )
    print("plot saved:", filename)
    plt.close(fig)


def create_rank_chart(
    data_dict,
    filename,
    title=None,
    x_label=None,
    y_label=None,
    special_colorize_and_hatch={},
    small=False,
):
    sorted_data = dict(
        sorted(data_dict.items(), key=lambda item: item[1], reverse=True)
    )
    values = list(sorted_data.values())
    labels = [i for i in range(len(values))]
    colors_hatches_tuples = [
        special_colorize_and_hatch.get(k) or ("black", None) for k in sorted_data.keys()
    ]

    if small:
        plt.figure(figsize=SMALL_FIGURE_SIZE)
    plt.bar(
        labels,
        values,
        color=list(map(lambda c_h: c_h[0], colors_hatches_tuples)),
        hatch=list(map(lambda c_h: c_h[1], colors_hatches_tuples)),
    )
    plt.locator_params(axis="x", integer=True)
    plt.locator_params(axis="y", integer=True)

    handles = [
        Patch(facecolor=c_h[0], hatch=c_h[1])
        for name, c_h in special_colorize_and_hatch.items()
        if c_h in colors_hatches_tuples
    ]
    names = [
        name
        for name, c_h in special_colorize_and_hatch.items()
        if c_h in colors_hatches_tuples
    ]
    if handles:
        plt.legend(handles=handles, labels=names)

    if x_label:
        plt.xlabel(x_label)
    if y_label:
        plt.ylabel(y_label)
    plt.savefig(
        filename, bbox_inches="tight", format="pdf", metadata={"CreationDate": None}
    )
    print("plot saved:", filename)
    plt.close()


def create_time_plot(
    time_series, labels, filename, title=None, colors=None, linestyles=None
):
    TEXT_SCALE = 0.8
    figsize = (3.5, 2.5)
    default_font_size = plt.rcParamsDefault["font.size"]
    figure_scale = figsize[0] / (SMALL_FIGURE_SIZE[0] / 2)
    font_size = default_font_size * figure_scale * TEXT_SCALE

    def scaled(param):
        return plt.rcParamsDefault[param] * figure_scale

    rc = {
        "font.size": font_size,
        "axes.labelsize": font_size,
        "xtick.labelsize": font_size * 0.9,
        "ytick.labelsize": font_size * 0.9,
        "legend.fontsize": font_size * 0.85,
        "lines.linewidth": scaled("lines.linewidth"),
        "axes.linewidth": scaled("axes.linewidth"),
        "xtick.major.width": scaled("xtick.major.width"),
        "ytick.major.width": scaled("ytick.major.width"),
        "xtick.major.size": scaled("xtick.major.size"),
        "ytick.major.size": scaled("ytick.major.size"),
    }

    color_list = color_list_for(labels=labels, color_assoc=colors)
    linestyle_list = assoc_list_for(labels, linestyles, kind="linestyle")

    with plt.rc_context(rc):
        fig, ax = plt.subplots(figsize=figsize, layout="constrained")
        for i, (time_list, label) in enumerate(zip(time_series, labels)):
            x = list(map(to_minutes, sorted(time_list)))
            y = list(range(1, len(time_list) + 1))
            color = None if color_list is None else color_list[i]
            linestyle = "solid" if linestyle_list is None else linestyle_list[i]
            ax.plot(x, y, label=label, color=color, linestyle=linestyle)
        ax.axis("auto")
        ax.xaxis.set_major_formatter(FuncFormatter(format_metric_suffix))
        ax.yaxis.set_major_formatter(FuncFormatter(format_metric_suffix))
        ax.legend(
            loc="lower left",
            bbox_to_anchor=(0.0, 1.0),
            borderaxespad=0.0,
            frameon=False,
            labelspacing=0.1,
            handlelength=2.2,
            handletextpad=0.5,
        )

        ax.set_xlabel("Time (min)")
        ax.set_ylabel("Number of crashes")

        fig.savefig(
            filename, bbox_inches="tight", format="pdf", metadata={"CreationDate": None}
        )
    print("plot saved:", filename)
    plt.close(fig)


def faulting_function_unwrap_pthread_kill(datum):
    if datum["report"]["faulting_function"] != "pthread_kill":
        return datum["report"]["faulting_function"]

    hit_libc = False
    for frame in datum["report"]["faulting_thread"]["frames"]:
        is_std_function = (
            "libc.so" in frame["module"] or "libstdc++.so" in frame["module"]
        )
        if hit_libc and not is_std_function:
            s = frame.get("symbol", {})
            return s.get("function_name")
        hit_libc = is_std_function


def faulting_filename(aflt_datum, expected_application, uses_relative_filenames=False):
    expected_prefix = f"/root/sci-apps-fuzz/build/{expected_application}/"
    executable = aflt_datum["command_line"][0]
    if not executable.startswith(expected_prefix):
        raise ValueError(
            "Unexpected executable path. This function may not operate correctly on your directory structure."
        )

    if uses_relative_filenames:
        expected_prefix = ""

    buckets = aflt_datum["bucket"]["inputs"]
    if len(buckets) == 0:
        raise ValueError("`bucket.inputs` should never be empty; check AFLTriage data.")
    top_bucket = buckets[0]

    if "/libc.so.6 " in top_bucket:
        return "libc"
    if (
        top_bucket.startswith("/usr/lib/gcc/x86_64-linux-gnu")
        and "include/c++/" in top_bucket
    ):
        return "libstdc++"
    if "/libgfortran.so.5 " in top_bucket:
        return "libgfortran"

    if not top_bucket.startswith(expected_prefix):
        print("WARNING: file with unrecognized prefix:", top_bucket)
        return "(unknown)"
    spl = top_bucket.rsplit(":", 1)
    if len(spl) != 2:
        print(f"WARNING: '{top_bucket}' does not split into (filename, line_number)")
        return "(unknown)"
    filename, line_num = spl
    if not is_nonneg_integer(line_num):
        print(f"WARNING: '{top_bucket}' has invalid line_number")
        return "(unknown)"

    try:
        r = str(Path(filename).relative_to(Path(expected_prefix)))
        return r
    except ValueError:
        print(f"WARNING: '{filename}' not relative to prefix '{expected_prefix}'")
        return "(unknown)"


def parser_or_core_filename(filename, application):
    if filename in ["libc", "libstdc++", "libgfortran"]:
        return "standard library"
    if filename == "(unknown)":
        return "unknown"

    r = LazyJsonData("../common/file_classification.json")[application].get(filename)
    if r is None or "kind" not in r:
        return "unclassified"
    else:
        return r["kind"]


def application_or_library_filename(filename, application):
    if filename in ["libc", "libstdc++", "libgfortran"]:
        return "standard library"
    if filename == "(unknown)":
        return "unknown"

    r = LazyJsonData("../common/file_classification.json")[application].get(filename)
    if r is None or "belongs_to" not in r:
        return "unclassified"
    else:
        return r["belongs_to"]


def extract_asan_check_name(datum):
    ts = datum["report"].get("terse_summary")
    if ts is not None and ts.startswith("ASAN_"):
        slug = ts.split("_")[1]
        if slug.lower() == "free":
            slug = "invalid-pointer-free"
        if slug.lower() == "out":
            slug = "out-of-memory"
        return asan_unslug(slug)
    else:
        return None


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="generates plots and stats from databases created by cwtriage and afltriage",
        usage="plot.py -c cwtriage-crashes.json -a afltriage-crashes/ -p path/to/plots/",
    )
    subparsers = parser.add_subparsers()

    parser_all = subparsers.add_parser("plot-all")
    parser_all.add_argument(
        "-d",
        "--fuzz_fs_dir",
        dest="shared_fuzz_fs",
        help="SHARED_FUZZ_FS directory with multiple applications to plot. Must have the expected structure.",
        required=True,
    )
    parser_all.add_argument(
        "--crashes-over-time-fuzzer-name",
        dest="crashes_over_time_fuzzer_names",
        metavar="NAME|APP:NAME,..",
        type=parse_fuzzer_run_names,
        help=(
            "restrict the crashes-over-time plots to the fuzzer run NAME, i.e. to the "
            "crashes found in syncdir/fuzzer-*-NAME. Give a single name to use it for "
            "every application, or a per-application mapping such as "
            "'enzo:123456abcdef,gromacs:123456abcdef'; a bare name is the "
            "default for the applications the mapping does not name. By default every "
            "run in the syncdir is combined, which mixes runs that started at "
            "different times. This is probably not what you want."
        ),
        default={},
    )
    parser_all.set_defaults(func=read_plot_all)

    return parser.parse_args(argv[1:])


def read_data(c_file, a_dir):
    print(f"read_data(): cwtriage file {c_file}")
    print(f"read_data(): afltriage directory {a_dir}")

    cw_data_raw = []
    with open(c_file) as f:
        for line in f:
            cw_data_raw.append(json.loads(line))
    cw_data_raw = [
        {**d, **parse_afl_input_name(d["entry"]["orig_filename"].split("/")[-1])}
        for d in cw_data_raw
    ]
    cw_data = list(
        filter(lambda d: d["entry"]["info"]["stack"] is not None, cw_data_raw)
    )
    if len(cw_data_raw) != len(cw_data):
        print(
            f"WARNING: {len(cw_data_raw) - len(cw_data)} of {len(cw_data_raw)} entries discarded because analysis failed"
        )

    aflt_data = []
    for root, dirs, files in os.walk(a_dir):
        for filename in files:
            with open(os.path.join(root, filename)) as f:
                aflt_data.append(json.load(f))

    return (aflt_data, cw_data)


def match_cluster_to_cw_report(cluster, cw_data):
    matches = list(
        filter(lambda d: d["entry"]["orig_filename"] == cluster["testcase"], cw_data)
    )
    if len(matches) == 0:
        print(f"WARNING: file {cluster['testcase']} did not match")
    return matches


def cluster_classify(cluster, cw_data):
    matches = match_cluster_to_cw_report(cluster, cw_data)
    r = (
        "Unclassified (failed)"
        if len(matches) == 0
        else matches[0]["entry"]["info"]["classification"]
        .replace("_", " ")
        .lower()
        .title()
    )
    if r == "Unknown" and extract_asan_check_name(cluster) is not None:
        r = "ASAN-Triaged"
    return r


def cluster_main_tag(cluster, cw_data):
    matches = match_cluster_to_cw_report(cluster, cw_data)
    return (
        "(failed)"
        if len(matches) == 0
        else matches[0]["entry"]["info"]["extra"][1].split(": ")[1].split(" ")[0]
    )


def read_plot_all(args):
    shared_fuzz_fs = os.path.abspath(os.path.expanduser(args["shared_fuzz_fs"]))
    crashes_over_time_fuzzer_names = args.get("crashes_over_time_fuzzer_names") or {}
    print(f"plot_all(): shared fuzz directory {shared_fuzz_fs}")
    print("reading in data..", file=sys.stderr)

    unused = (
        set(crashes_over_time_fuzzer_names) - {None} - set(applications_pretty_print)
    )
    if unused:
        print(
            f"WARNING: --crashes-over-time-fuzzer-name names unplotted "
            f"application(s): {', '.join(sorted(unused))}",
            file=sys.stderr,
        )

    data = {}
    # per-application plots
    for application in next(os.walk(shared_fuzz_fs))[1]:
        if application not in applications_pretty_print.keys():
            continue
        afltriage_dir = os.path.join(shared_fuzz_fs, application, "triage/afltriage/")
        cwtriage_file = os.path.join(
            shared_fuzz_fs, application, "triage/cw/crashes.json"
        )
        plots_dir = os.path.join(shared_fuzz_fs, "plots", application)

        os.makedirs(plots_dir, exist_ok=True)
        with open(os.path.join(plots_dir, "run.txt"), "w") as sys.stdout:
            (aflt_data, cw_data) = read_data(cwtriage_file, afltriage_dir)
            data[application] = (aflt_data, cw_data)
            plot_one(
                aflt_data,
                cw_data,
                application,
                plots_dir,
                crashes_over_time_fuzzer_name=crashes_over_time_fuzzer_names.get(
                    application, crashes_over_time_fuzzer_names.get(None)
                ),
            )

    # cross-application plots
    plot_all(shared_fuzz_fs, data)


def plot_all(shared_fuzz_fs, data):
    plots_dir = os.path.join(shared_fuzz_fs, "plots/all/")
    os.makedirs(plots_dir, exist_ok=True)
    with open(os.path.join(plots_dir, "run.txt"), "w") as sys.stdout:
        print("processing data..", file=sys.stderr)
        cluster_classification = {
            application: count_distinct_values(
                aflt_data, lambda c: cluster_classify(c, cw_data)
            )
            for (application, (aflt_data, cw_data)) in data.items()
        }
        asan = {
            application: count_distinct_values(aflt_data, extract_asan_check_name)
            for (application, (aflt_data, cw_data)) in data.items()
        }
        by_parser_or_core = {
            application: count_distinct_values(
                aflt_data,
                lambda d: parser_or_core_filename(
                    faulting_filename(
                        d,
                        application,
                        applications_debug_use_relative_filenames[application],
                    ),
                    application,
                ).title(),
            )
            for (application, (aflt_data, cw_data)) in data.items()
        }
        by_application_or_library = {
            application: count_distinct_values(
                aflt_data,
                lambda d: application_or_library_filename(
                    faulting_filename(
                        d,
                        application,
                        applications_debug_use_relative_filenames[application],
                    ),
                    application,
                ).title(),
            )
            for (application, (aflt_data, cw_data)) in data.items()
        }

        print("drawing..", file=sys.stderr)

        create_stacked_bar_chart_all(
            cluster_classification,
            os.path.join(plots_dir, "exploitable_class_cluster.pdf"),
            y_label="Number of crash clusters",
            label_order=exploitable_verdicts,
            colors=exploitable_verdict_colors,
        )
        create_stacked_bar_chart_all(
            {k: v for (k, v) in asan.items() if k is not None},
            os.path.join(plots_dir, "asan_detections.pdf"),
            y_label="Number of crash clusters",
            legend_loc="outside right center",
        )
        create_stacked_bar_chart_all(
            by_application_or_library,
            os.path.join(plots_dir, "application_or_library.pdf"),
            y_label="Number of crash clusters",
            label_order=[
                "Unclassified",
                "Unknown",
                "Standard Library",
                "Library",
                "Application",
            ],
            small=True,
        )
        create_stacked_bar_chart_all(
            by_parser_or_core,
            os.path.join(plots_dir, "parser_or_core.pdf"),
            y_label="Number of crash clusters",
            label_order=[
                "Unclassified",
                "Unknown",
                "Standard Library",
                "Non-Parser",
                "Combined",
                "Parser",
            ],
            small=True,
        )

        print_unclassified(data)


def print_unclassified(data):
    for application, (aflt_data, cw_data) in data.items():
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            unclassified = []
            for d in aflt_data:
                f = faulting_filename(
                    d,
                    application,
                    applications_debug_use_relative_filenames[application],
                )
                if (
                    application_or_library_filename(f, application) == "unclassified"
                    or parser_or_core_filename(f, application) == "unclassified"
                ):
                    unclassified.append(f)
            unclassified = list(dict.fromkeys(unclassified))
            if len(unclassified) == 0:
                continue
            for f in unclassified:
                tmp.write(f.encode())
                tmp.write(b"\n")
            print(f"unclassified for {application}: {tmp.name}")
            print(
                f"to tag them, run /root/sci-apps-fuzz/src/common/tag_files.sh {application} {tmp.name} /root/sci-apps-fuzz/src/common/file_classification.json"
            )


def plot_one(
    aflt_data, cw_data, application, plots_dir, crashes_over_time_fuzzer_name=None
):
    by_signal = count_distinct_values(
        aflt_data, lambda x: x["report"]["stop_info"]["signal_name"]
    )
    by_faulting_function = count_distinct_values(
        aflt_data, faulting_function_unwrap_pthread_kill
    )
    by_faulting_file = count_distinct_values(
        aflt_data,
        lambda d: faulting_filename(
            d, application, applications_debug_use_relative_filenames[application]
        ),
    )
    asan = count_distinct_values(aflt_data, extract_asan_check_name)
    asan_clusters_e_pe = len(
        list(
            filter(
                lambda c: (
                    extract_asan_check_name(c) is not None
                    and cluster_classify(c, cw_data)
                    in ["Exploitable", "Probably Exploitable"]
                ),
                aflt_data,
            )
        )
    )

    total_clust = len(aflt_data)
    num_segv = by_signal.get("SIGSEGV", 0)
    num_abrt = by_signal.get("SIGABRT", 0)
    num_heap = sum(
        [
            asan.get(t, 0)
            for t in asan.keys()
            if t is not None and (t.startswith("Heap") or t == "Invalid Pointer Free")
        ]
    )
    num_stack = sum(
        [asan.get(t, 0) for t in asan.keys() if t is not None and t.startswith("Stack")]
    )
    num_other_abort = num_abrt - num_heap - num_stack
    num_other = total_clust - num_segv - num_abrt

    max_execs_seen = max(
        int(parse_afl_input_name(d["testcase"].split("/")[-1]).get("execs", "0"))
        for d in aflt_data
    )
    max_time_seen = max(
        int(parse_afl_input_name(d["testcase"].split("/")[-1]).get("time", "0"))
        for d in aflt_data
    )

    print(f"Total clusters: {len(aflt_data)}")
    print(f"max value of execs: {max_execs_seen}")
    print(f"max value of time: {to_days(max_time_seen)} days")
    print(f"Clusters by signal: {by_signal}")
    print("Abort clusters from ASAN:", asan)
    print(
        f"{asan_clusters_e_pe} clusters were ASAN-reported issues that were also classified 'Exploitable' or 'Probably Exploitable'."
    )
    print("Clusters by faulting function:", by_faulting_function)
    print("Clusters by faulting file:", by_faulting_file)
    print(
        "Stats for table (total, segv, heap_memory_safety, stack_memory_safety, other_abort, other):"
    )
    print(
        f" >> {len(aflt_data)} & {num_segv} & {num_heap} & {num_stack} & {num_other_abort} & {num_other}"
    )

    cluster_classification = count_distinct_values(
        aflt_data, lambda c: cluster_classify(c, cw_data)
    )
    main_tag = count_distinct_values(aflt_data, lambda c: cluster_main_tag(c, cw_data))
    print("Cluster classification:", cluster_classification)
    print("Cluster main tag:", main_tag)

    create_rank_chart(
        by_faulting_function,
        os.path.join(plots_dir, "rank_by_function.pdf"),
        "Ranking of functions by number of crash clusters",
        x_label="Faulting function",
        y_label="Frequency (clusters in function)",
        special_colorize_and_hatch={
            "(unknown)": ("gray", "O"),
        },
        small=True,
    )
    create_rank_chart(
        by_faulting_file,
        os.path.join(plots_dir, "rank_by_file.pdf"),
        "Ranking of code files by number of crash clusters",
        x_label="Faulting file",
        y_label="Frequency (clusters in file)",
        special_colorize_and_hatch={
            "libc": ("red", "-"),
            "libstdc++": ("dodgerblue", "/"),
            "libgfortran": ("lime", "\\"),
            "(unknown)": ("gray", "O"),
        },
        small=True,
    )

    cw_data_over_time = select_timed_crashes(
        select_fuzzer_run(cw_data, crashes_over_time_fuzzer_name)
    )
    times = list(map(crash_time, cw_data_over_time))
    exploitable_times = list(
        map(
            crash_time,
            filter(
                lambda d: (
                    d["entry"]["info"]["classification"]
                    in ["EXPLOITABLE", "PROBABLY_EXPLOITABLE"]
                ),
                cw_data_over_time,
            ),
        )
    )
    unknown_times = list(
        map(
            crash_time,
            filter(
                lambda d: d["entry"]["info"]["classification"] in ["UNKNOWN"],
                cw_data_over_time,
            ),
        )
    )
    create_time_plot(
        [times, exploitable_times, unknown_times],
        crashes_over_time_series,
        os.path.join(plots_dir, "crashes_over_time.pdf"),
        colors=crashes_over_time_colors,
        linestyles=crashes_over_time_linestyles,
    )


def main(argv):
    args = parse_args(argv)
    args.func(vars(args))


if __name__ == "__main__":
    main(sys.argv)
