from app import addition_loading_render_fix_policy as policy


def test_scope_render_happens_after_loading_flag_is_cleared() -> None:
    source = f"before:{policy._SCOPE_RENDER_BEFORE_CLEAR}:after"
    patched = policy._patch_addition_scope_render(source)

    assert policy._SCOPE_RENDER_BEFORE_CLEAR not in patched
    assert policy._SCOPE_RENDER_AFTER_CLEAR in patched
    assert patched.index("state.loading.delete(scope)") < patched.index('if(scope==="history")renderHistory()')


def test_unrelated_html_is_unchanged() -> None:
    source = "<html><body>sem script operacional</body></html>"
    assert policy._patch_addition_scope_render(source) == source
