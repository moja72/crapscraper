from app.addition_operational_legacy_suppression_policy import _suppress_legacy_addition_renderers


def test_suppresses_real_legacy_script_and_style_attributes():
    html = """
    <html><body>
      <style data-new-product-workflow>.addition-shell{display:grid}</style>
      <script data-new-product-workflow-script>window.oldWorkflow = true;</script>
      <script data-addition-one-click>window.oldOneClick = true;</script>
      <script data-addition-operational-ui>window.newOperational = true;</script>
    </body></html>
    """

    result = _suppress_legacy_addition_renderers(html)

    assert "data-new-product-workflow>" not in result
    assert "data-new-product-workflow-script" not in result
    assert "data-addition-one-click" not in result
    assert "data-addition-operational-ui" in result
    assert "window.newOperational = true" in result


def test_does_not_remove_unrelated_scripts():
    html = '<script data-process-observability>window.processes = true;</script>'
    assert _suppress_legacy_addition_renderers(html) == html
