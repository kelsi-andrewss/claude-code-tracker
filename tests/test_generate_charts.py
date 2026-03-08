"""Tests for generate-charts.py dashboard features (story-565).

Since generate-charts.py is a top-level script (not importable as a module),
we test pure functions via exec extraction, and test the full HTML pipeline
via subprocess invocation.
"""
import json
import os
import subprocess
import sys
import re

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
import storage

SRC_DIR = os.path.join(os.path.dirname(__file__), '..', 'src')
GENERATE_CHARTS = os.path.join(SRC_DIR, 'generate-charts.py')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_functions():
    """Extract classify_error and format_duration from generate-charts.py
    without running the whole script."""
    with open(GENERATE_CHARTS, encoding='utf-8') as f:
        source = f.read()

    # Extract format_duration
    match = re.search(
        r'^(def format_duration\(seconds\):.*?)(?=\n\S|\Z)',
        source, re.MULTILINE | re.DOTALL,
    )
    assert match, "Could not extract format_duration"
    format_duration_src = match.group(1)

    # Extract classify_error
    match = re.search(
        r'^(def classify_error\(event\):.*?)(?=\n\S|\Z)',
        source, re.MULTILINE | re.DOTALL,
    )
    assert match, "Could not extract classify_error"
    classify_error_src = match.group(1)

    ns = {}
    exec(format_duration_src, ns)
    exec("import re", ns)
    exec(classify_error_src, ns)
    return ns['format_duration'], ns['classify_error']


format_duration, classify_error = _extract_functions()


def _setup_tracking(tmp_path, turns=None, agents=None, friction=None,
                    key_prompts=None):
    """Create a tracking dir with DB, optional friction.json, and key-prompts.

    Returns (tracking_dir, output_html_path).
    """
    tracking_dir = str(tmp_path / 'tracking')
    os.makedirs(tracking_dir, exist_ok=True)
    storage.init_db(tracking_dir)

    if turns:
        storage.upsert_turns(tracking_dir, turns)

    if agents:
        for a in agents:
            storage.append_agent(tracking_dir, a)

    if friction is not None:
        friction_path = os.path.join(tracking_dir, 'friction.json')
        with open(friction_path, 'w', encoding='utf-8') as f:
            json.dump(friction, f)

    if key_prompts:
        prompts_dir = os.path.join(tracking_dir, 'key-prompts')
        os.makedirs(prompts_dir, exist_ok=True)
        for date, content in key_prompts.items():
            with open(os.path.join(prompts_dir, f'{date}.md'), 'w') as f:
                f.write(content)

    output_path = str(tmp_path / 'charts.html')
    return tracking_dir, output_path


def _run_generate(tracking_dir, output_path):
    """Run generate-charts.py and return (CompletedProcess, html_content)."""
    result = subprocess.run(
        [sys.executable, GENERATE_CHARTS, tracking_dir, output_path],
        capture_output=True, text=True,
    )
    html = ''
    if os.path.exists(output_path):
        with open(output_path, encoding='utf-8') as f:
            html = f.read()
    return result, html


def _make_turn(session_id, turn_index, date, model='claude-opus-4-20250514',
               input_tokens=1000, output_tokens=500,
               cache_creation_tokens=200, cache_read_tokens=300,
               total_tokens=2000, estimated_cost_usd=0.0567,
               duration_seconds=10, project='test-proj'):
    """Build a turn dict suitable for upsert_turns."""
    return {
        'session_id': session_id,
        'turn_index': turn_index,
        'date': date,
        'project': project,
        'turn_timestamp': f'{date}T10:00:00.000Z',
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
        'cache_creation_tokens': cache_creation_tokens,
        'cache_read_tokens': cache_read_tokens,
        'total_tokens': total_tokens,
        'estimated_cost_usd': estimated_cost_usd,
        'model': model,
        'duration_seconds': duration_seconds,
    }


def _make_agent(session_id, agent_id, agent_type, turns=2,
                input_tokens=300, output_tokens=150,
                estimated_cost_usd=0.05, model='claude-opus-4-20250514'):
    """Build an agent dict suitable for append_agent."""
    return {
        'timestamp': '2026-03-07T10:00:00.000Z',
        'session_id': session_id,
        'agent_id': agent_id,
        'agent_type': agent_type,
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
        'cache_creation_tokens': 0,
        'cache_read_tokens': 0,
        'total_tokens': input_tokens + output_tokens,
        'turns': turns,
        'estimated_cost_usd': estimated_cost_usd,
        'model': model,
    }


# ---------------------------------------------------------------------------
# AC 7: classify_error correctly classifies detail strings
# ---------------------------------------------------------------------------

class TestClassifyError:

    def test_validation_error(self):
        event = {'detail': 'InputValidationError: bad input', 'category': 'tool_error'}
        assert classify_error(event) == 'validation_error'

    def test_file_not_found_no_such_file(self):
        event = {'detail': 'No such file or directory: /tmp/x', 'category': 'tool_error'}
        assert classify_error(event) == 'file_not_found'

    def test_file_not_found_python_error(self):
        event = {'detail': 'FileNotFoundError: missing.py', 'category': 'tool_error'}
        assert classify_error(event) == 'file_not_found'

    def test_timeout_lowercase(self):
        event = {'detail': 'command timed out after 30s', 'category': 'command_failed'}
        assert classify_error(event) == 'timeout'

    def test_timeout_mixed_case(self):
        event = {'detail': 'Timeout waiting for response', 'category': 'tool_error'}
        assert classify_error(event) == 'timeout'

    def test_encoding_error_unicode(self):
        event = {'detail': "UnicodeDecodeError: 'utf-8' codec", 'category': 'tool_error'}
        assert classify_error(event) == 'encoding_error'

    def test_encoding_error_keyword(self):
        event = {'detail': 'bad encoding in file', 'category': 'tool_error'}
        assert classify_error(event) == 'encoding_error'

    def test_exit_code_for_command_failed(self):
        event = {'detail': 'Exit code 1\nnpm test failed', 'category': 'command_failed'}
        assert classify_error(event) == 'exit_code_1'

    def test_exit_code_127(self):
        event = {'detail': 'Exit code 127\ncommand not found', 'category': 'command_failed'}
        assert classify_error(event) == 'exit_code_127'

    def test_exit_code_not_extracted_for_non_command_failed(self):
        """Exit code regex only fires for category=command_failed."""
        event = {'detail': 'Exit code 1\nfailed', 'category': 'tool_error'}
        assert classify_error(event) == 'generic'

    def test_generic_fallback(self):
        event = {'detail': 'something unexpected happened', 'category': 'tool_error'}
        assert classify_error(event) == 'generic'

    def test_empty_detail(self):
        event = {'detail': '', 'category': 'tool_error'}
        assert classify_error(event) == 'generic'

    def test_none_detail(self):
        event = {'detail': None, 'category': 'tool_error'}
        assert classify_error(event) == 'generic'

    def test_missing_detail_key(self):
        event = {'category': 'tool_error'}
        assert classify_error(event) == 'generic'


# ---------------------------------------------------------------------------
# format_duration (utility, exercised in stats)
# ---------------------------------------------------------------------------

class TestFormatDuration:

    def test_zero(self):
        assert format_duration(0) == '0m'

    def test_negative(self):
        assert format_duration(-5) == '0m'

    def test_minutes_and_seconds(self):
        assert format_duration(125) == '2m 5s'

    def test_exact_minutes(self):
        assert format_duration(120) == '2m 0s'

    def test_hours_and_minutes(self):
        assert format_duration(3720) == '1h 2m'

    def test_one_hour_exactly(self):
        assert format_duration(3600) == '1h 0m'


# ---------------------------------------------------------------------------
# AC 1: Token composition stacked bar with 4 datasets
# ---------------------------------------------------------------------------

class TestTokenCompositionChart:

    def test_renders_4_datasets(self, tmp_path):
        turns = [
            _make_turn('s1', 0, '2026-03-07', input_tokens=100, output_tokens=50,
                        cache_creation_tokens=20, cache_read_tokens=30,
                        total_tokens=200),
        ]
        tracking_dir, output_path = _setup_tracking(tmp_path, turns=turns)
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert 'tokenComp' in html, "Token composition canvas not found"

        # Verify all 4 datasets are present in the JS
        assert 'INPUT_BY_DATE' in html
        assert 'CACHE_CREATE_BY_DATE' in html
        assert 'CACHE_READ_BY_DATE' in html
        assert 'OUTPUT_BY_DATE' in html

        # Verify the stacked bar chart references all 4
        token_comp_section = html[html.index('tokenComp'):]
        assert 'Input' in token_comp_section
        assert 'Cache creation' in token_comp_section
        assert 'Cache read' in token_comp_section
        assert 'Output' in token_comp_section


# ---------------------------------------------------------------------------
# AC 2: Input tokens stat card shows formatted total with commas
# ---------------------------------------------------------------------------

class TestInputTokensStatCard:

    def test_formatted_with_commas(self, tmp_path):
        turns = [
            _make_turn('s1', 0, '2026-03-07', input_tokens=1234567,
                        total_tokens=1234567),
        ]
        tracking_dir, output_path = _setup_tracking(tmp_path, turns=turns)
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert '1,234,567' in html, "Input tokens should be formatted with commas"

    def test_small_number_no_commas_needed(self, tmp_path):
        turns = [
            _make_turn('s1', 0, '2026-03-07', input_tokens=500, total_tokens=500),
        ]
        tracking_dir, output_path = _setup_tracking(tmp_path, turns=turns)
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0, f"stderr: {result.stderr}"
        # 500 doesn't need commas, just verify it appears in the stat card
        assert 'Input tokens' in html


# ---------------------------------------------------------------------------
# AC 3: Friction by skill chart only renders with non-null skill data
# ---------------------------------------------------------------------------

class TestFrictionBySkillChart:

    def test_renders_when_skill_data_exists(self, tmp_path):
        turns = [_make_turn('s1', 0, '2026-03-07')]
        friction = [
            {'date': '2026-03-07', 'category': 'tool_error', 'source': 'main',
             'tool_name': 'Bash', 'skill': 'commit', 'detail': 'failed',
             'session_id': 's1'},
        ]
        tracking_dir, output_path = _setup_tracking(
            tmp_path, turns=turns, friction=friction)
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert 'frictionSkill' in html
        assert 'FRICTION_SKILL_LABELS' in html
        assert 'FRICTION_SKILL_VALUES' in html

    def test_hidden_when_no_skill_data(self, tmp_path):
        turns = [_make_turn('s1', 0, '2026-03-07')]
        friction = [
            {'date': '2026-03-07', 'category': 'tool_error', 'source': 'main',
             'tool_name': 'Bash', 'skill': None, 'detail': 'failed',
             'session_id': 's1'},
        ]
        tracking_dir, output_path = _setup_tracking(
            tmp_path, turns=turns, friction=friction)
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert 'frictionSkill' not in html
        assert 'FRICTION_SKILL_LABELS' not in html

    def test_hidden_when_all_skills_null(self, tmp_path):
        """Events exist but none have a non-null skill field."""
        turns = [_make_turn('s1', 0, '2026-03-07')]
        friction = [
            {'date': '2026-03-07', 'category': 'command_failed', 'source': 'main',
             'tool_name': 'Bash', 'detail': 'Exit code 1', 'session_id': 's1'},
            {'date': '2026-03-07', 'category': 'tool_error', 'source': 'main',
             'tool_name': 'Read', 'detail': 'error', 'session_id': 's1'},
        ]
        tracking_dir, output_path = _setup_tracking(
            tmp_path, turns=turns, friction=friction)
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert 'frictionSkill' not in html


# ---------------------------------------------------------------------------
# AC 4: Retry resolution stat card only renders when retry_total > 0
# ---------------------------------------------------------------------------

class TestRetryResolutionStatCard:

    def test_renders_when_retries_exist(self, tmp_path):
        turns = [_make_turn('s1', 0, '2026-03-07')]
        friction = [
            {'date': '2026-03-07', 'category': 'retry', 'source': 'main',
             'resolved': True, 'detail': 'retry 1', 'session_id': 's1'},
            {'date': '2026-03-07', 'category': 'retry', 'source': 'main',
             'resolved': False, 'detail': 'retry 2', 'session_id': 's1'},
        ]
        tracking_dir, output_path = _setup_tracking(
            tmp_path, turns=turns, friction=friction)
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert 'Retry resolution' in html
        assert '50.0%' in html  # 1 of 2 resolved
        assert '1 of 2 retries succeeded' in html

    def test_hidden_when_no_retries(self, tmp_path):
        turns = [_make_turn('s1', 0, '2026-03-07')]
        friction = [
            {'date': '2026-03-07', 'category': 'tool_error', 'source': 'main',
             'tool_name': 'Bash', 'detail': 'failed', 'session_id': 's1'},
        ]
        tracking_dir, output_path = _setup_tracking(
            tmp_path, turns=turns, friction=friction)
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert 'Retry resolution' not in html

    def test_hidden_when_no_friction(self, tmp_path):
        turns = [_make_turn('s1', 0, '2026-03-07')]
        tracking_dir, output_path = _setup_tracking(tmp_path, turns=turns)
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert 'Retry resolution' not in html


# ---------------------------------------------------------------------------
# AC 5: Agent cost-per-turn chart renders with correct cost/turns ratio
# ---------------------------------------------------------------------------

class TestAgentCostPerTurnChart:

    def test_renders_cpt_chart(self, tmp_path):
        turns = [_make_turn('s1', 0, '2026-03-07')]
        agents = [
            _make_agent('s1', 'a1', 'coder', turns=4, estimated_cost_usd=0.20),
            _make_agent('s1', 'a2', 'tester', turns=2, estimated_cost_usd=0.10),
        ]
        tracking_dir, output_path = _setup_tracking(
            tmp_path, turns=turns, agents=agents)
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert 'agentCPT' in html
        assert 'AGENT_CPT' in html
        assert 'Cost per turn by agent type' in html

    def test_cpt_values_correct(self, tmp_path):
        """Verify the computed cost-per-turn values in the JS array."""
        turns = [_make_turn('s1', 0, '2026-03-07')]
        agents = [
            _make_agent('s1', 'a1', 'coder', turns=4, estimated_cost_usd=0.20),
            _make_agent('s1', 'a2', 'tester', turns=2, estimated_cost_usd=0.10),
        ]
        tracking_dir, output_path = _setup_tracking(
            tmp_path, turns=turns, agents=agents)
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0, f"stderr: {result.stderr}"

        # Extract the AGENT_CPT array from the JS
        cpt_match = re.search(r'const AGENT_CPT = (\[.*?\]);', html)
        assert cpt_match, "AGENT_CPT constant not found"
        cpt_values = json.loads(cpt_match.group(1))

        # Extract the AGENT_LABELS to know the order
        labels_match = re.search(r'const AGENT_LABELS = (\[.*?\]);', html)
        assert labels_match, "AGENT_LABELS constant not found"
        labels = json.loads(labels_match.group(1))

        # Build label -> cpt mapping
        cpt_by_type = dict(zip(labels, cpt_values))

        # coder: 0.20 / 4 = 0.05, tester: 0.10 / 2 = 0.05
        assert cpt_by_type['coder'] == 0.05
        assert cpt_by_type['tester'] == 0.05

    def test_cpt_zero_when_no_turns(self, tmp_path):
        """Agent with 0 turns should produce 0 cost-per-turn."""
        turns = [_make_turn('s1', 0, '2026-03-07')]
        agents = [
            _make_agent('s1', 'a1', 'coder', turns=0, estimated_cost_usd=0.10),
        ]
        tracking_dir, output_path = _setup_tracking(
            tmp_path, turns=turns, agents=agents)
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0, f"stderr: {result.stderr}"
        cpt_match = re.search(r'const AGENT_CPT = (\[.*?\]);', html)
        assert cpt_match
        cpt_values = json.loads(cpt_match.group(1))
        assert cpt_values == [0]

    def test_no_agent_section_when_no_agents(self, tmp_path):
        turns = [_make_turn('s1', 0, '2026-03-07')]
        tracking_dir, output_path = _setup_tracking(tmp_path, turns=turns)
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert 'agentCPT' not in html
        assert 'AGENT_CPT' not in html
        assert 'AGENT_LABELS' not in html


# ---------------------------------------------------------------------------
# AC 6: Error section only renders when error events exist
# ---------------------------------------------------------------------------

class TestErrorSection:

    def test_renders_when_error_events_exist(self, tmp_path):
        turns = [_make_turn('s1', 0, '2026-03-07')]
        friction = [
            {'date': '2026-03-07', 'category': 'tool_error', 'source': 'main',
             'tool_name': 'Bash', 'detail': 'InputValidationError', 'session_id': 's1'},
            {'date': '2026-03-07', 'category': 'command_failed', 'source': 'main',
             'tool_name': 'Bash', 'detail': 'Exit code 1', 'session_id': 's1'},
        ]
        tracking_dir, output_path = _setup_tracking(
            tmp_path, turns=turns, friction=friction)
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert 'section-header errors' in html
        assert 'errorTypes' in html
        assert 'errorTools' in html
        assert 'errorTrend' in html
        assert 'ERROR_TYPE_LABELS' in html
        assert 'ERROR_TYPE_VALUES' in html

    def test_hidden_when_no_error_categories(self, tmp_path):
        """Friction with non-error categories should not produce error section."""
        turns = [_make_turn('s1', 0, '2026-03-07')]
        friction = [
            {'date': '2026-03-07', 'category': 'correction', 'source': 'main',
             'detail': 'wrong approach', 'session_id': 's1'},
            {'date': '2026-03-07', 'category': 'retry', 'source': 'main',
             'resolved': True, 'detail': 'retry', 'session_id': 's1'},
        ]
        tracking_dir, output_path = _setup_tracking(
            tmp_path, turns=turns, friction=friction)
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert 'section-header errors' not in html
        assert 'errorTypes' not in html

    def test_hidden_when_no_friction(self, tmp_path):
        turns = [_make_turn('s1', 0, '2026-03-07')]
        tracking_dir, output_path = _setup_tracking(tmp_path, turns=turns)
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert 'section-header errors' not in html

    def test_cascade_error_triggers_error_section(self, tmp_path):
        turns = [_make_turn('s1', 0, '2026-03-07')]
        friction = [
            {'date': '2026-03-07', 'category': 'cascade_error', 'source': 'main',
             'tool_name': 'Bash', 'detail': 'cascade failure', 'session_id': 's1'},
        ]
        tracking_dir, output_path = _setup_tracking(
            tmp_path, turns=turns, friction=friction)
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert 'section-header errors' in html


# ---------------------------------------------------------------------------
# AC 8: All new JS constants are emitted and referenced correctly
# ---------------------------------------------------------------------------

class TestJSConstantsIntegrity:

    def test_all_core_constants_defined(self, tmp_path):
        """Verify every JS const referenced in chart constructors is defined."""
        turns = [_make_turn('s1', 0, '2026-03-07')]
        agents = [_make_agent('s1', 'a1', 'coder')]
        friction = [
            {'date': '2026-03-07', 'category': 'tool_error', 'source': 'main',
             'tool_name': 'Bash', 'skill': 'commit', 'detail': 'error',
             'session_id': 's1'},
            {'date': '2026-03-07', 'category': 'retry', 'source': 'main',
             'resolved': True, 'detail': 'retry', 'session_id': 's1'},
        ]
        tracking_dir, output_path = _setup_tracking(
            tmp_path, turns=turns, agents=agents, friction=friction)
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0, f"stderr: {result.stderr}"

        # Extract JS block
        script_match = re.search(r'<script>(.*?)</script>', html, re.DOTALL)
        assert script_match, "No script block found"
        js = script_match.group(1)

        # Find all const declarations
        defined = set(re.findall(r'const (\w+)\s*=', js))

        # Find all identifiers used as data references (data: SOMETHING)
        # and label references in chart configs
        used_in_data = set(re.findall(r'(?:data|labels):\s*(\b[A-Z][A-Z_]+\b)', js))

        # Every used constant must be defined
        undefined = used_in_data - defined
        assert not undefined, f"Undefined JS constants referenced: {undefined}"

    def test_agent_constants_present_with_agents(self, tmp_path):
        turns = [_make_turn('s1', 0, '2026-03-07')]
        agents = [_make_agent('s1', 'a1', 'coder')]
        tracking_dir, output_path = _setup_tracking(
            tmp_path, turns=turns, agents=agents)
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0
        for const in ['AGENT_LABELS', 'AGENT_COSTS', 'AGENT_COUNTS', 'AGENT_CPT']:
            assert f'const {const}' in html, f"{const} not defined in JS"

    def test_friction_constants_present_with_friction(self, tmp_path):
        turns = [_make_turn('s1', 0, '2026-03-07')]
        friction = [
            {'date': '2026-03-07', 'category': 'tool_error', 'source': 'main',
             'tool_name': 'Bash', 'detail': 'error', 'session_id': 's1'},
        ]
        tracking_dir, output_path = _setup_tracking(
            tmp_path, turns=turns, friction=friction)
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0
        for const in ['FRICTION_DATES', 'FRICTION_MAIN', 'FRICTION_SUB',
                       'FRICTION_CAT_LABELS', 'FRICTION_CAT_VALUES',
                       'FRICTION_TOOL_LABELS', 'FRICTION_TOOL_VALUES',
                       'FRICTION_RATE_DATES', 'FRICTION_RATE_VALUES']:
            assert f'const {const}' in html, f"{const} not defined in JS"

    def test_error_constants_present_with_errors(self, tmp_path):
        turns = [_make_turn('s1', 0, '2026-03-07')]
        friction = [
            {'date': '2026-03-07', 'category': 'tool_error', 'source': 'main',
             'tool_name': 'Bash', 'detail': 'error', 'session_id': 's1'},
        ]
        tracking_dir, output_path = _setup_tracking(
            tmp_path, turns=turns, friction=friction)
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0
        for const in ['ERROR_TYPE_LABELS', 'ERROR_TYPE_VALUES',
                       'ERROR_TOOL_LABELS', 'ERROR_TOOL_VALUES',
                       'ERROR_DATES', 'ERROR_DATE_VALUES']:
            assert f'const {const}' in html, f"{const} not defined in JS"

    def test_no_agent_constants_without_agents(self, tmp_path):
        turns = [_make_turn('s1', 0, '2026-03-07')]
        tracking_dir, output_path = _setup_tracking(tmp_path, turns=turns)
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0
        assert 'AGENT_LABELS' not in html
        assert 'AGENT_CPT' not in html


# ---------------------------------------------------------------------------
# AC 9: Section order: Stats -> Cost & Usage -> Agents -> Friction
#        -> Errors -> Key Prompts -> Time
# ---------------------------------------------------------------------------

class TestSectionOrder:

    def test_full_section_order(self, tmp_path):
        """With all sections active, verify correct ordering."""
        turns = [_make_turn('s1', 0, '2026-03-07')]
        agents = [_make_agent('s1', 'a1', 'coder')]
        friction = [
            {'date': '2026-03-07', 'category': 'tool_error', 'source': 'main',
             'tool_name': 'Bash', 'detail': 'error', 'session_id': 's1'},
        ]
        key_prompts = {
            '2026-03-07': '## 2026-03-07 -- test\n**Category**: feature\n',
        }
        tracking_dir, output_path = _setup_tracking(
            tmp_path, turns=turns, agents=agents, friction=friction,
            key_prompts=key_prompts)
        # Add skill data for full section coverage
        storage.replace_session_skills(tracking_dir, 's1', [{
            'session_id': 's1', 'date': '2026-03-07', 'project': 'test-proj',
            'skill_name': 'commit', 'duration_seconds': 5, 'success': 1,
        }])
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0, f"stderr: {result.stderr}"

        # Find positions of section markers
        stats_pos = html.index('class="stats"')
        cost_pos = html.index('section-header cost')
        agents_pos = html.index('section-header agents')
        skills_pos = html.index('section-header skills')
        friction_pos = html.index('section-header friction')
        errors_pos = html.index('section-header errors')
        prompts_pos = html.index('section-header prompts')
        time_pos = html.index('section-header time')

        assert stats_pos < cost_pos < agents_pos < skills_pos < friction_pos < errors_pos < prompts_pos < time_pos, \
            "Section order must be: Stats < Cost & Usage < Agents < Skills < Friction < Errors < Key Prompts < Time"

    def test_optional_sections_omitted_preserve_order(self, tmp_path):
        """Without agents/friction/errors, remaining sections keep order."""
        turns = [_make_turn('s1', 0, '2026-03-07')]
        key_prompts = {
            '2026-03-07': '## 2026-03-07 -- test\n**Category**: feature\n',
        }
        tracking_dir, output_path = _setup_tracking(
            tmp_path, turns=turns, key_prompts=key_prompts)
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0, f"stderr: {result.stderr}"

        stats_pos = html.index('class="stats"')
        cost_pos = html.index('section-header cost')
        prompts_pos = html.index('section-header prompts')
        time_pos = html.index('section-header time')

        assert stats_pos < cost_pos < prompts_pos < time_pos

        # Optional sections should not appear
        assert 'section-header agents' not in html
        assert 'section-header skills' not in html
        assert 'section-header friction' not in html
        assert 'section-header errors' not in html


# ---------------------------------------------------------------------------
# AC 10: Existing functionality — basic smoke tests
# ---------------------------------------------------------------------------

class TestBasicSmoke:

    def test_generates_html_with_minimal_data(self, tmp_path):
        turns = [_make_turn('s1', 0, '2026-03-07')]
        tracking_dir, output_path = _setup_tracking(tmp_path, turns=turns)
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert html.startswith('<!DOCTYPE html>')
        assert 'chart.js' in html.lower() or 'Chart' in html
        assert 'test-proj' in html

    def test_exits_zero_with_no_data(self, tmp_path):
        """Empty DB -> script exits 0, no output file."""
        tracking_dir, output_path = _setup_tracking(tmp_path)
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0
        assert html == ''  # No output file created

    def test_multi_date_aggregation(self, tmp_path):
        turns = [
            _make_turn('s1', 0, '2026-03-07'),
            _make_turn('s2', 0, '2026-03-08'),
        ]
        tracking_dir, output_path = _setup_tracking(tmp_path, turns=turns)
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert '2026-03-07' in html
        assert '2026-03-08' in html

    def test_cost_stat_card_present(self, tmp_path):
        turns = [_make_turn('s1', 0, '2026-03-07', estimated_cost_usd=1.2345)]
        tracking_dir, output_path = _setup_tracking(tmp_path, turns=turns)
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0
        assert '$1.23' in html  # formatted to 2 decimal places

    def test_cache_read_percentage(self, tmp_path):
        turns = [
            _make_turn('s1', 0, '2026-03-07', cache_read_tokens=800,
                        total_tokens=1000),
        ]
        tracking_dir, output_path = _setup_tracking(tmp_path, turns=turns)
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0
        assert '80.0%' in html


# ---------------------------------------------------------------------------
# Skills section tests
# ---------------------------------------------------------------------------

class TestSkillsSection:

    def test_renders_when_data_exists(self, tmp_path):
        turns = [_make_turn('s1', 0, '2026-03-07')]
        tracking_dir, output_path = _setup_tracking(tmp_path, turns=turns)
        # Insert skill data directly
        storage.replace_session_skills(tracking_dir, 's1', [{
            'session_id': 's1', 'date': '2026-03-07', 'project': 'test-proj',
            'skill_name': 'commit', 'duration_seconds': 5, 'success': 1,
        }])
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert 'section-header skills' in html
        assert 'skillCount' in html
        assert 'skillSuccess' in html
        assert 'skillTimeline' in html

    def test_hidden_when_no_data(self, tmp_path):
        turns = [_make_turn('s1', 0, '2026-03-07')]
        tracking_dir, output_path = _setup_tracking(tmp_path, turns=turns)
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert 'section-header skills' not in html
        assert 'SKILL_LABELS' not in html

    def test_stat_card_shows_count(self, tmp_path):
        turns = [_make_turn('s1', 0, '2026-03-07')]
        tracking_dir, output_path = _setup_tracking(tmp_path, turns=turns)
        storage.replace_session_skills(tracking_dir, 's1', [
            {'session_id': 's1', 'date': '2026-03-07', 'project': 'test-proj',
             'skill_name': 'commit', 'duration_seconds': 5, 'success': 1},
            {'session_id': 's1', 'date': '2026-03-07', 'project': 'test-proj',
             'skill_name': 'audit', 'duration_seconds': 10, 'success': 1},
            {'session_id': 's1', 'date': '2026-03-07', 'project': 'test-proj',
             'skill_name': 'commit', 'duration_seconds': 3, 'success': 0},
        ])
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert 'Skill invocations' in html
        assert '66.7%' in html  # 2 of 3 succeeded

    def test_js_constants_present(self, tmp_path):
        turns = [_make_turn('s1', 0, '2026-03-07')]
        tracking_dir, output_path = _setup_tracking(tmp_path, turns=turns)
        storage.replace_session_skills(tracking_dir, 's1', [{
            'session_id': 's1', 'date': '2026-03-07', 'project': 'test-proj',
            'skill_name': 'commit', 'duration_seconds': 5, 'success': 1,
        }])
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0, f"stderr: {result.stderr}"
        for const in ['SKILL_LABELS', 'SKILL_COUNTS', 'SKILL_SUCCESS', 'SKILL_FAIL',
                       'SKILL_TIMELINE_DATES', 'SKILL_TIMELINE_VALUES']:
            assert f'const {const}' in html, f"{const} not defined in JS"

    def test_chart_data_values_correct(self, tmp_path):
        """Verify SKILL_LABELS/COUNTS/SUCCESS/FAIL hold correct aggregated values."""
        turns = [_make_turn('s1', 0, '2026-03-07')]
        tracking_dir, output_path = _setup_tracking(tmp_path, turns=turns)
        storage.replace_session_skills(tracking_dir, 's1', [
            {'session_id': 's1', 'date': '2026-03-07', 'project': 'test-proj',
             'skill_name': 'commit', 'duration_seconds': 5, 'success': 1},
            {'session_id': 's1', 'date': '2026-03-07', 'project': 'test-proj',
             'skill_name': 'commit', 'duration_seconds': 3, 'success': 0},
            {'session_id': 's1', 'date': '2026-03-07', 'project': 'test-proj',
             'skill_name': 'audit', 'duration_seconds': 10, 'success': 1},
        ])
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0, f"stderr: {result.stderr}"

        labels = json.loads(re.search(r'const SKILL_LABELS = (\[.*?\]);', html).group(1))
        counts = json.loads(re.search(r'const SKILL_COUNTS = (\[.*?\]);', html).group(1))
        success = json.loads(re.search(r'const SKILL_SUCCESS = (\[.*?\]);', html).group(1))
        fail = json.loads(re.search(r'const SKILL_FAIL = (\[.*?\]);', html).group(1))

        data = {l: {'count': c, 'success': s, 'fail': f}
                for l, c, s, f in zip(labels, counts, success, fail)}

        assert data['commit'] == {'count': 2, 'success': 1, 'fail': 1}
        assert data['audit'] == {'count': 1, 'success': 1, 'fail': 0}

    def test_sorted_by_count_descending(self, tmp_path):
        """SKILL_LABELS should be ordered by invocation count descending."""
        turns = [_make_turn('s1', 0, '2026-03-07')]
        tracking_dir, output_path = _setup_tracking(tmp_path, turns=turns)
        storage.replace_session_skills(tracking_dir, 's1', [
            # 3 ship
            {'session_id': 's1', 'date': '2026-03-07', 'project': 'test-proj',
             'skill_name': 'ship', 'duration_seconds': 1, 'success': 1},
            {'session_id': 's1', 'date': '2026-03-07', 'project': 'test-proj',
             'skill_name': 'ship', 'duration_seconds': 1, 'success': 1},
            {'session_id': 's1', 'date': '2026-03-07', 'project': 'test-proj',
             'skill_name': 'ship', 'duration_seconds': 1, 'success': 1},
            # 2 commit
            {'session_id': 's1', 'date': '2026-03-07', 'project': 'test-proj',
             'skill_name': 'commit', 'duration_seconds': 1, 'success': 1},
            {'session_id': 's1', 'date': '2026-03-07', 'project': 'test-proj',
             'skill_name': 'commit', 'duration_seconds': 1, 'success': 1},
            # 1 audit
            {'session_id': 's1', 'date': '2026-03-07', 'project': 'test-proj',
             'skill_name': 'audit', 'duration_seconds': 1, 'success': 1},
        ])
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0, f"stderr: {result.stderr}"

        labels = json.loads(re.search(r'const SKILL_LABELS = (\[.*?\]);', html).group(1))
        assert labels == ['ship', 'commit', 'audit']

    def test_timeline_multi_date(self, tmp_path):
        """SKILL_TIMELINE_DATES/VALUES should aggregate across multiple dates."""
        turns = [
            _make_turn('s1', 0, '2026-03-07'),
            _make_turn('s2', 0, '2026-03-08'),
        ]
        tracking_dir, output_path = _setup_tracking(tmp_path, turns=turns)
        # 2 skills on 03-07
        storage.replace_session_skills(tracking_dir, 's1', [
            {'session_id': 's1', 'date': '2026-03-07', 'project': 'test-proj',
             'skill_name': 'commit', 'duration_seconds': 5, 'success': 1},
            {'session_id': 's1', 'date': '2026-03-07', 'project': 'test-proj',
             'skill_name': 'audit', 'duration_seconds': 3, 'success': 1},
        ])
        # 1 skill on 03-08
        storage.replace_session_skills(tracking_dir, 's2', [
            {'session_id': 's2', 'date': '2026-03-08', 'project': 'test-proj',
             'skill_name': 'commit', 'duration_seconds': 2, 'success': 1},
        ])
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0, f"stderr: {result.stderr}"

        dates = json.loads(re.search(r'const SKILL_TIMELINE_DATES = (\[.*?\]);', html).group(1))
        values = json.loads(re.search(r'const SKILL_TIMELINE_VALUES = (\[.*?\]);', html).group(1))
        timeline = dict(zip(dates, values))

        assert timeline == {'2026-03-07': 2, '2026-03-08': 1}

    def test_all_failures_zero_success_rate(self, tmp_path):
        """When every skill invocation fails, success rate should be 0.0%."""
        turns = [_make_turn('s1', 0, '2026-03-07')]
        tracking_dir, output_path = _setup_tracking(tmp_path, turns=turns)
        storage.replace_session_skills(tracking_dir, 's1', [
            {'session_id': 's1', 'date': '2026-03-07', 'project': 'test-proj',
             'skill_name': 'commit', 'duration_seconds': 5, 'success': 0},
            {'session_id': 's1', 'date': '2026-03-07', 'project': 'test-proj',
             'skill_name': 'audit', 'duration_seconds': 3, 'success': 0},
        ])
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert '0.0%' in html

    def test_all_successes_100_rate(self, tmp_path):
        """When every skill invocation succeeds, success rate should be 100.0%."""
        turns = [_make_turn('s1', 0, '2026-03-07')]
        tracking_dir, output_path = _setup_tracking(tmp_path, turns=turns)
        storage.replace_session_skills(tracking_dir, 's1', [
            {'session_id': 's1', 'date': '2026-03-07', 'project': 'test-proj',
             'skill_name': 'commit', 'duration_seconds': 5, 'success': 1},
            {'session_id': 's1', 'date': '2026-03-07', 'project': 'test-proj',
             'skill_name': 'audit', 'duration_seconds': 3, 'success': 1},
        ])
        result, html = _run_generate(tracking_dir, output_path)

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert '100.0%' in html
