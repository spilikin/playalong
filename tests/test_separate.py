import io
import warnings

from playalong.separate import clean_progress, quiet_library_warnings


def test_redrawn_progress_lines_clear_what_was_there():
    out = io.StringIO()
    stream = clean_progress(out)
    stream.write("\rEstimated time remaining: 10.00 seconds")
    stream.write("\rEstimated time remaining: 0.00 seconds")
    stream.write("\n")
    assert out.getvalue().split("\r")[-1] == "Estimated time remaining: 0.00 seconds\x1b[K\n"


def test_only_the_known_library_warnings_are_hidden():
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        with quiet_library_warnings():
            warnings.warn("A window was not provided. A rectangular window will be applied", UserWarning)
            warnings.warn("`torch.cuda.amp.autocast(args...)` is deprecated.", FutureWarning)
            warnings.warn("CUDA is not available or torch_xla is imported. Disabling autocast.", UserWarning)
            warnings.warn("`torch.backends.cuda.sdp_kernel()` is deprecated.", FutureWarning)
            warnings.warn("something else went wrong", UserWarning)
    assert [str(w.message) for w in seen] == ["something else went wrong"]
