# Plan 02-03 Summary: Recording Modes, Weekly Schedule Engine & CLI

## Status: COMPLETE

### Overview
Plan 02-03 implemented per-camera recording mode configuration (Continuous, Scheduled, Event, Off), the 7x24 weekly schedule grid engine with timezone and Daylight Saving Time (DST) active window evaluation, audio recording validation against camera hardware capabilities, retention caps, and local admin CLI subcommands (`nvr recording set-mode`, `nvr recording set-schedule`, `nvr recording set-audio`, `nvr recording set-retention`) per decisions D-37, D-40, and requirements REC-02, REC-03, and REC-11.

### Tasks Completed:

1. **Task 1: Weekly schedule evaluator and RecordingSettingsService**
   - Implemented `src/vizenlink_nvr/services/schedule.py`:
     - `WeeklySchedule`: 7 days x 24 hours weekly recording schedule matrix.
     - Built-in presets: `always()`, `never()`, `weekdays()`, `weekends()`, `business_hours()`, `nights()`.
     - `is_active_at(dt: datetime, tz_name: str) -> bool`: Accurately maps UTC timestamp to site timezone, extracts day-of-week and hour slot, and evaluates active recording state seamlessly across standard time and daylight saving time (DST) shifts.
     - `from_spec(...)`: Constructs schedule from preset name, JSON string, dictionary, or raw boolean matrix.
     - `to_dict()` and `to_json()`: Clean serialization.
   - Implemented `src/vizenlink_nvr/services/recording_settings.py`:
     - `RecordingMode`: Typed StrEnum (`continuous`, `scheduled`, `event`, `off`).
     - `get_or_create_recording_settings`: Fetches or initializes default settings (continuous, always schedule, audio off) for registered cameras; raises `CameraNotFoundError` for unknown serials.
     - `set_recording_mode`: Validates mode and updates `recording_settings` table.
     - `set_recording_schedule`: Parses schedule spec and persists JSON.
     - `set_recording_audio`: Verifies camera hardware capabilities from `camera_capabilities` (`raw_json`); raises `AudioNotSupportedError` if camera hardware explicitly lacks audio support.
     - `set_recording_retention`: Configures retention days and maximum gigabytes cap.
     - `should_record_now`: Computes real-time recording readiness (True for `continuous` and `event`; False for `off`; schedule-driven for `scheduled`).
   - Created unit tests:
     - `tests/unit/test_recording_schedule.py`: 6 tests verifying presets, hour/day mutators, JSON roundtrip, multi-timezone conversions (New York, Tokyo), and DST transition boundary checks.
     - `tests/unit/test_recording_modes.py`: 6 tests verifying default initialization, mode updates, schedule updates, audio capability enforcement, retention validation, and real-time recording evaluation.

2. **Task 2: CLI recording subcommands (set-mode, set-schedule, set-audio, set-retention)**
   - Created `src/vizenlink_nvr/cli/recording.py`:
     - `recording_app` registered under `nvr recording` in `src/vizenlink_nvr/cli/app.py`.
     - `nvr recording set-mode --serial <SERIAL> --mode <MODE>`
     - `nvr recording set-schedule --serial <SERIAL> --schedule <SPEC>`
     - `nvr recording set-audio --serial <SERIAL> --enabled / --disabled`
     - `nvr recording set-retention --serial <SERIAL> [--days N] [--max-gb GB]`
     - Enforces D-16: all CLI options use TyperOption flags, no positional arguments.
   - Created `tests/integration/test_cli_recording_settings.py`:
     - 5 tests verifying CLI invocations, `--json` structured outputs, invalid mode rejection (`ExitCode.INVALID_INPUT`), unknown camera rejection (`ExitCode.NOT_FOUND`), mute camera audio refusal, retention caps, and rejection of positional arguments.

### Verification Results:
- `uv run pytest tests/unit/test_recording_modes.py tests/unit/test_recording_schedule.py tests/integration/test_cli_recording_settings.py -x -q`: 17 passed in 0.46s.
- `uv run pytest tests/unit/test_cli_password_options.py`: 2 passed (All CLI commands use TyperOption, no prohibited password options).
- `uv run ruff check src tests sim tools`: All checks passed.
- `uv run mypy src`: Success: no issues found in 74 source files.
- Quick suite: 33 passed in 0.54s.
