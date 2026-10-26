import json
import sqlite3
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from terminal_manager import codex_sessions as cs
from terminal_manager.app import TerminalManagerApp
from terminal_manager.model import ShellInfo, WindowInfo
from terminal_manager.recovery import recovery_command, launch_recovery_terminal
from terminal_manager.store import save_shell, save_runtime_session, load_runtime_session, recovery_candidates

SID = "01a0431b-cf5e-7bb1-8086-eb59604ec754"
OTHER = "01a11a9c-edcd-75d2-a3f8-eede358a3eb2"


@pytest.fixture
def catalog(tmp_path):
    with sqlite3.connect(tmp_path / "state_5.sqlite") as db:
        db.execute('CREATE TABLE threads(id,cwd,title,source,updated_at,rollout_path,archived)')
        db.execute('INSERT INTO threads VALUES(?,?,?,?,?,?,?)', (SID, str(tmp_path), 'original prompt', 'cli', 1, '/unused', 0))
    (tmp_path / 'session_index.jsonl').write_text(json.dumps({'id': SID, 'thread_name': 'Original conversation'})+'\n')
    return cs.sessions(str(tmp_path))


def test_metadata_is_read_only_and_uses_session_label(catalog):
    assert catalog[0]['label'] == 'Original conversation'
    assert catalog[0]['id'] == SID


def test_resume_uses_exact_id_without_prompt_or_command_replay(tmp_path, catalog):
    with patch('terminal_manager.codex_sessions.shutil.which', return_value='/safe/codex'):
        argv = cs.resume_argv(SID, str(tmp_path), str(tmp_path))
    assert argv == ['env', f'CODEX_HOME={tmp_path}', '/safe/codex', 'resume', SID, '-C', str(tmp_path)]
    assert '--last' not in argv and 'exec' not in argv


def test_missing_session_does_not_launch_any_terminal(tmp_path):
    with patch('terminal_manager.codex_sessions.metadata', return_value=None), patch('terminal_manager.recovery.subprocess.Popen') as launch:
        ok, error = launch_recovery_terminal(tmp_path, codex_session_id=SID)
    assert not ok and '找不到' in error
    launch.assert_not_called()


def test_invalid_id_cannot_become_shell_input(tmp_path):
    with pytest.raises(ValueError):
        cs.resume_argv('$(touch bad)', str(tmp_path))


def test_gnome_codex_restore_has_role_and_structured_arguments(tmp_path):
    with patch('terminal_manager.recovery.shutil.which', return_value='/usr/bin/gnome-terminal'), patch('terminal_manager.codex_sessions.resume_argv', return_value=['/safe/codex', 'resume', SID]):
        command = recovery_command(tmp_path, 'unique', codex_session_id=SID)
    assert command[-5:] == ['--role=unique', '--', '/safe/codex', 'resume', SID]


def test_live_session_is_not_opened_twice():
    app = object.__new__(TerminalManagerApp)
    app.root = Mock()
    app._recovery_entries = [{'codex_session_id': SID}]
    app._recovery_index = app._recovery_skipped_count = 0
    with patch('terminal_manager.codex_sessions.is_live', return_value=True), patch('terminal_manager.app.launch_recovery_terminal') as launch:
        app._restore_next_window()
    launch.assert_not_called()
    assert app._recovery_index == 1 and app._recovery_skipped_count == 1


def test_persisted_tty_reuse_cannot_change_directory():
    app = object.__new__(TerminalManagerApp)
    app.tty_bindings = {}
    shell = ShellInfo('s','0x1',123,'/dev/pts/3','original','idle','','','/original',None,'',0,0)
    window = WindowInfo('0x1',0,100,0,0,800,600,'gnome-terminal','','test')
    assert app._directory_for(shell,window,'main',{'/dev/pts/3':'/wrong-project'}) == '/original'
    app.tty_bindings={'0x1':{'main':'/dev/pts/4'}}
    assert app._directory_for(shell,window,'main',{'/dev/pts/4':'/verified-project'}) == '/verified-project'


def test_detect_requires_live_cli_and_unique_title(catalog):
    item=catalog[0]
    process={'id':SID,'home':item['home'],'cwd':item['cwd'],'tty':'/dev/pts/4'}
    title='⠋ Original conversation | project'
    assert cs.detect(title,item['cwd'],'',[process],catalog)['codex_session_id']==SID
    assert cs.detect(title,item['cwd'],'',[],catalog)=={}
    assert cs.detect('different conversation',item['cwd'],'',[process],catalog)=={}
    ambiguous=catalog+[{**item,'id':OTHER}]
    assert cs.detect(title,item['cwd'],'',[{**process,'id':''}],ambiguous)=={}
    assert cs.detect(title,item['cwd'],'',[{**process,'id':''},{**process,'id':'','tty':'/dev/pts/5'}],catalog)=={}


def test_slash_resume_title_overrides_stale_startup_argv(catalog):
    item=catalog[0]
    newer={**item,'id':OTHER,'label':'Changed conversation'}
    process={'id':SID,'home':item['home'],'cwd':item['cwd'],'tty':'/dev/pts/4'}
    assert cs.detect('Changed conversation | project',item['cwd'],'/dev/pts/4',[process],catalog+[newer])['codex_session_id']==OTHER


def test_server_and_exec_are_not_interactive_sessions():
    assert cs.parse_cli(['/safe/codex','app-server'])==(False,'')
    assert cs.parse_cli(['/safe/codex','exec','resume',SID])==(False,'')
    assert cs.parse_cli(['node','/safe/codex','resume',SID])==(True,SID)


def test_session_fields_survive_empty_scan_and_clean_exit(tmp_path,monkeypatch):
    monkeypatch.setenv('XDG_STATE_HOME',str(tmp_path))
    entry={'shell_id':'s','window_id':'0x1','name':'name','cwd':'/work','codex_session_id':SID,'codex_cwd':'/work','codex_home':'/home/me/.codex'}
    save_runtime_session(clean_shutdown=False,entries=[entry])
    assert load_runtime_session()['entries']==[entry]
    save_runtime_session(clean_shutdown=False,entries=[])
    save_runtime_session(clean_shutdown=True,entries=[])
    assert recovery_candidates()[0]['codex_session_id']==SID


def test_manual_link_on_closed_record_is_not_hidden_by_old_snapshot(tmp_path,monkeypatch):
    monkeypatch.setenv('XDG_STATE_HOME',str(tmp_path))
    save_runtime_session(clean_shutdown=False,entries=[{'shell_id':'s','window_id':'0x1','name':'name','cwd':'/work'}])
    shell=ShellInfo('s','0x1',0,'','name','ended','','','/work',None,'',0,0,codex_session_id=SID,codex_cwd='/work',codex_home='/home/me/.codex')
    save_shell(shell)
    assert recovery_candidates()[0]['codex_session_id']==SID
