import logging
import sys
import unittest

# Match the import style in test_stt_impl.py: pytest will already add
# this directory to sys.path during test collection, but make it explicit
# so the file works when run with `python -m unittest` too.
sys.path.append(".")

from main import _parse_job_metadata, _build_per_job_config


class TestParseJobMetadata(unittest.TestCase):
    def test_none_returns_empty(self):
        self.assertEqual(_parse_job_metadata(None), {})

    def test_empty_string_returns_empty(self):
        self.assertEqual(_parse_job_metadata(""), {})

    def test_invalid_json_returns_empty_with_warning(self):
        with self.assertLogs(level="WARNING") as cm:
            self.assertEqual(_parse_job_metadata("not json"), {})
        self.assertTrue(any("unparseable job metadata" in msg for msg in cm.output))

    def test_bare_json_string_returns_empty_with_warning(self):
        with self.assertLogs(level="WARNING") as cm:
            self.assertEqual(_parse_job_metadata('"es-ES"'), {})
        self.assertTrue(any("expected JSON object" in msg for msg in cm.output))

    def test_json_null_returns_empty_with_warning(self):
        with self.assertLogs(level="WARNING") as cm:
            self.assertEqual(_parse_job_metadata("null"), {})
        self.assertTrue(any("expected JSON object" in msg for msg in cm.output))

    def test_empty_object_returns_empty_no_warning(self):
        # assertNoLogs is 3.10+; use a manual approach for portability
        logger = logging.getLogger()
        with self.assertLogs(logger, level="WARNING") as cm:
            # assertLogs requires at least one record; emit a sentinel
            logger.warning("sentinel")
            result = _parse_job_metadata("{}")
        self.assertEqual(result, {})
        # Only the sentinel should be present
        self.assertEqual(len(cm.output), 1)
        self.assertIn("sentinel", cm.output[0])

    def test_object_with_no_language_key(self):
        self.assertEqual(_parse_job_metadata('{"other": "x"}'), {})

    def test_language_explicit_null_returns_empty_no_warning(self):
        logger = logging.getLogger()
        with self.assertLogs(logger, level="WARNING") as cm:
            logger.warning("sentinel")
            result = _parse_job_metadata('{"language": null}')
        self.assertEqual(result, {})
        self.assertEqual(len(cm.output), 1)
        self.assertIn("sentinel", cm.output[0])

    def test_language_string(self):
        self.assertEqual(
            _parse_job_metadata('{"language": "es-ES"}'),
            {"language": "es-ES"},
        )

    def test_language_list(self):
        self.assertEqual(
            _parse_job_metadata('{"language": ["en-US", "es-ES"]}'),
            {"language": ["en-US", "es-ES"]},
        )

    def test_language_empty_string_returns_empty_with_warning(self):
        with self.assertLogs(level="WARNING") as cm:
            self.assertEqual(_parse_job_metadata('{"language": ""}'), {})
        self.assertTrue(any("must be non-empty string" in msg for msg in cm.output))

    def test_language_empty_list_returns_empty_with_warning(self):
        with self.assertLogs(level="WARNING") as cm:
            self.assertEqual(_parse_job_metadata('{"language": []}'), {})
        self.assertTrue(any("must be non-empty string" in msg for msg in cm.output))

    def test_language_list_with_non_strings_returns_empty_with_warning(self):
        with self.assertLogs(level="WARNING") as cm:
            self.assertEqual(_parse_job_metadata('{"language": [1, 2]}'), {})
        self.assertTrue(any("must be non-empty string" in msg for msg in cm.output))

    def test_language_number_returns_empty_with_warning(self):
        with self.assertLogs(level="WARNING") as cm:
            self.assertEqual(_parse_job_metadata('{"language": 42}'), {})
        self.assertTrue(any("must be non-empty string" in msg for msg in cm.output))

    def test_other_keys_ignored_silently(self):
        self.assertEqual(
            _parse_job_metadata('{"language": "en-US", "phrase_list": ["foo"]}'),
            {"language": "en-US"},
        )


class TestBuildPerJobConfig(unittest.TestCase):
    def _base_config(self):
        # Mirrors the live_captions.azure shape from agent-speech-processing.yaml
        return {
            "live_captions": {
                "provider": "azure",
                "azure": {
                    "speech_region": "eastus",
                    "speech_key": "test-key",
                    "language": "en-US",
                },
            },
        }

    def test_no_metadata_returns_input_unchanged(self):
        cfg = self._base_config()
        result = _build_per_job_config(cfg, None)
        self.assertEqual(result["live_captions"]["azure"]["language"], "en-US")

    def test_empty_metadata_returns_input_unchanged(self):
        cfg = self._base_config()
        result = _build_per_job_config(cfg, "")
        self.assertEqual(result["live_captions"]["azure"]["language"], "en-US")

    def test_language_string_overrides(self):
        cfg = self._base_config()
        result = _build_per_job_config(cfg, '{"language": "es-ES"}')
        self.assertEqual(result["live_captions"]["azure"]["language"], "es-ES")
        # Other Azure keys preserved
        self.assertEqual(result["live_captions"]["azure"]["speech_region"], "eastus")
        self.assertEqual(result["live_captions"]["azure"]["speech_key"], "test-key")

    def test_language_list_overrides(self):
        cfg = self._base_config()
        result = _build_per_job_config(
            cfg, '{"language": ["en-US", "es-ES"]}'
        )
        self.assertEqual(
            result["live_captions"]["azure"]["language"], ["en-US", "es-ES"]
        )

    def test_input_config_not_mutated(self):
        cfg = self._base_config()
        snapshot = {
            "live_captions": {
                "provider": "azure",
                "azure": {
                    "speech_region": "eastus",
                    "speech_key": "test-key",
                    "language": "en-US",
                },
            },
        }
        _build_per_job_config(cfg, '{"language": "es-ES"}')
        # Critical isolation check: the input is unchanged
        self.assertEqual(cfg, snapshot)

    def test_consecutive_calls_do_not_bleed(self):
        cfg = self._base_config()
        first = _build_per_job_config(cfg, '{"language": "es-ES"}')
        second = _build_per_job_config(cfg, '{"language": "fr-FR"}')
        self.assertEqual(first["live_captions"]["azure"]["language"], "es-ES")
        self.assertEqual(second["live_captions"]["azure"]["language"], "fr-FR")
        # Original still untouched
        self.assertEqual(cfg["live_captions"]["azure"]["language"], "en-US")

    def test_missing_live_captions_azure_path_is_built(self):
        cfg = {"live_captions": {"provider": "azure"}}  # no "azure" sub-dict
        result = _build_per_job_config(cfg, '{"language": "es-ES"}')
        self.assertEqual(result["live_captions"]["azure"]["language"], "es-ES")
        # Original still untouched
        self.assertNotIn("azure", cfg["live_captions"])

    def test_missing_live_captions_entirely(self):
        cfg = {"provider_irrelevant": True}  # no "live_captions" at all
        result = _build_per_job_config(cfg, '{"language": "es-ES"}')
        self.assertEqual(result["live_captions"]["azure"]["language"], "es-ES")
        self.assertNotIn("live_captions", cfg)

    def test_bad_metadata_falls_back_to_input(self):
        cfg = self._base_config()
        # Warning will be logged by _parse_job_metadata; we just verify the
        # fallback behavior here.
        with self.assertLogs(level="WARNING"):
            result = _build_per_job_config(cfg, '{"language": 42}')
        self.assertEqual(result["live_captions"]["azure"]["language"], "en-US")


if __name__ == "__main__":
    unittest.main()
