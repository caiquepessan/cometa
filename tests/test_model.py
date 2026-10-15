import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cometa import model  # noqa: E402
from cometa.model import AppState, Stopwatch, Store, format_hms, split_time  # noqa: E402


class Clock:
    def __init__(self, t: float = 1_000_000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


class StopwatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = Clock()
        patcher = mock.patch.object(model, "now", self.clock)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_pause_resume_accumulates(self) -> None:
        sw = Stopwatch()
        sw.start()
        self.clock.t += 90
        self.assertAlmostEqual(sw.elapsed(), 90)
        sw.pause()
        self.assertEqual(sw.status, "paused")
        self.clock.t += 1000  # paused time does not count
        self.assertAlmostEqual(sw.elapsed(), 90)
        sw.start()
        self.clock.t += 10.5
        self.assertAlmostEqual(sw.elapsed(), 100.5)

    def test_stop_keeps_final_time_until_next_start(self) -> None:
        sw = Stopwatch()
        sw.start()
        self.clock.t += 42
        sw.stop()
        self.assertEqual(sw.status, "finished")
        self.clock.t += 500
        self.assertAlmostEqual(sw.elapsed(), 42)
        sw.start()  # a new count, from zero
        self.assertEqual(sw.status, "running")
        self.clock.t += 3
        self.assertAlmostEqual(sw.elapsed(), 3)

    def test_status_lifecycle(self) -> None:
        sw = Stopwatch()
        self.assertEqual(sw.status, "idle")
        sw.start()
        self.assertEqual(sw.status, "running")
        self.clock.t += 1
        sw.pause()
        self.assertEqual(sw.status, "paused")
        sw.reset()
        self.assertEqual(sw.status, "idle")

    def test_reset_zeroes_and_stops(self) -> None:
        sw = Stopwatch()
        sw.start()
        self.clock.t += 5
        sw.reset()
        self.assertFalse(sw.running)
        self.assertEqual(sw.elapsed(), 0)

    def test_clock_going_backwards_never_rewinds(self) -> None:
        sw = Stopwatch(accumulated=30)
        sw.start()
        self.clock.t -= 3600
        self.assertEqual(sw.elapsed(), 30)

    def test_double_start_keeps_original_start(self) -> None:
        sw = Stopwatch()
        sw.start()
        self.clock.t += 20
        sw.start()
        self.clock.t += 5
        self.assertAlmostEqual(sw.elapsed(), 25)


class StoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name))
        self.clock = Clock()
        patcher = mock.patch.object(model, "now", self.clock)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_running_stopwatch_keeps_counting_across_restarts(self) -> None:
        sw = Stopwatch(name="Projeto", accent=2, accumulated=12.5)
        sw.start()
        done = Stopwatch(name="Outro", accumulated=7)
        done.stop()
        self.store.save(AppState([sw, done], geometry="abc", on_top=False))

        self.clock.t += 3600  # the app was closed for an hour
        state = self.store.load()
        self.assertEqual([s.name for s in state.stopwatches], ["Projeto", "Outro"])
        self.assertEqual(state.geometry, "abc")
        self.assertFalse(state.on_top)
        self.assertEqual(state.stopwatches[1].status, "finished")
        loaded = state.stopwatches[0]
        self.assertTrue(loaded.running)
        self.assertEqual(loaded.accent, 2)
        self.assertAlmostEqual(loaded.elapsed(), 3612.5, places=2)

    def test_missing_file_gives_empty_state(self) -> None:
        self.assertEqual(self.store.load().stopwatches, [])

    def test_corrupt_file_is_set_aside_not_overwritten(self) -> None:
        self.store.path.write_text("{ not json", encoding="utf-8")
        self.assertEqual(self.store.load().stopwatches, [])
        kept = list(Path(self.tmp.name).glob("state.corrupt-*.json"))
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].read_text(encoding="utf-8"), "{ not json")

    def test_invalid_entries_are_skipped_or_sanitized(self) -> None:
        self.store.path.write_text(json.dumps({"stopwatches": [
            "nope",
            {"name": "", "accumulated": -5, "started_at": "x"},
            {"name": "Ok", "accumulated": 7, "started_at": None},
        ]}), encoding="utf-8")
        names = [(s.name, s.accumulated) for s in self.store.load().stopwatches]
        self.assertEqual(names, [("Ok", 7.0)])

    def test_default_store_picks_up_data_from_pre_rename_builds(self) -> None:
        base = Path(self.tmp.name)
        legacy = base / "Cronometro"
        legacy.mkdir()
        (legacy / "state.json").write_text(json.dumps({"stopwatches": [{"name": "Antigo"}]}),
                                           encoding="utf-8")
        with mock.patch.object(model, "_data_base", return_value=base), \
                mock.patch.dict("os.environ", {"COMETA_DATA_DIR": ""}):
            store = Store()
            state = store.load()
            self.assertEqual([s.name for s in state.stopwatches], ["Antigo"])
            store.save(state)
        self.assertTrue((base / "Cometa" / "state.json").exists())

    def test_save_leaves_no_temp_files(self) -> None:
        self.store.save(AppState([Stopwatch()]))
        self.store.save(AppState([Stopwatch(), Stopwatch()]))
        files = sorted(p.name for p in Path(self.tmp.name).iterdir())
        self.assertEqual(files, ["state.json"])


class FormatTests(unittest.TestCase):
    def test_split_and_format(self) -> None:
        self.assertEqual(split_time(3723.456), (1, 2, 3, 45))
        self.assertEqual(format_hms(0), "00:00:00")
        self.assertEqual(format_hms(100 * 3600 + 59), "100:00:59")
        self.assertEqual(split_time(-3), (0, 0, 0, 0))


if __name__ == "__main__":
    unittest.main()
