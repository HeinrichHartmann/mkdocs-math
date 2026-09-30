"""Tests for the article notes-folder helpers (notes_nav option)."""

from pathlib import Path

from ..plugin import Plugin


def make_plugin(**config):
    plugin = Plugin()
    plugin.config = {'notes_nav': False, 'notes_exclude': [], **config}
    return plugin


def test_notes_nav_off_by_default():
    defaults = dict(Plugin.config_scheme)
    assert defaults['notes_nav'].default is False
    assert defaults['notes_exclude'].default == []


def test_title_from_stem_keeps_casing():
    plugin = make_plugin()
    assert plugin._title_from_stem('RC-I-Interface') == 'RC I Interface'
    assert plugin._title_from_stem('V2-Skeleton') == 'V2 Skeleton'
    assert plugin._title_from_stem('2026-08-07-review') == 'review'
    assert plugin._title_from_stem('2026-08-14 - Regulator Calculus') == 'Regulator Calculus'


def test_notes_dir_is_exact_stem():
    plugin = make_plugin()
    article = Path('/docs/Articles/2026-07-10-Foo.md')
    assert plugin._notes_dir(article) == Path('/docs/Articles/2026-07-10-Foo.d')


def test_note_files_respects_exclude(tmp_path):
    for name in ['Intro.md', 'log.md', 'inbox.md', 'Sketch.md', 'data.txt']:
        (tmp_path / name).write_text('x')
    plugin = make_plugin(notes_exclude=['log.md', 'inbox*'])
    assert [f.name for f in plugin._note_files(tmp_path)] == ['Intro.md', 'Sketch.md']


def test_quick_frontmatter_rejects_non_mapping():
    plugin = make_plugin()
    assert plugin._quick_frontmatter('---\ntitle: T\n---\nbody') == {'title': 'T'}
    assert plugin._quick_frontmatter('---\n- a list\n---\n') == {}
    assert plugin._quick_frontmatter('no frontmatter') == {}
