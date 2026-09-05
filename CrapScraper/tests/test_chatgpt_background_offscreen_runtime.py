from app.additions import chatgpt_background_project_runtime as runtime


class _Session:
    def __init__(self):
        self.bounds = None

    def send(self, method, payload=None):
        if method == "Browser.getWindowForTarget":
            return {"windowId": 7}
        if method == "Browser.setWindowBounds":
            self.bounds = payload
            return {}
        raise AssertionError(method)


class _Context:
    def __init__(self, session):
        self.session = session

    def new_cdp_session(self, page):
        return self.session


class _Page:
    def __init__(self):
        self.session = _Session()
        self.context = _Context(self.session)
        self.init_scripts = []
        self.evaluated = []

    def add_init_script(self, script):
        self.init_scripts.append(script)

    def evaluate(self, script):
        self.evaluated.append(script)


def test_background_window_is_parked_offscreen_not_minimized():
    page = _Page()
    assert runtime._park_offscreen(page) is True
    payload = page.session.bounds
    assert payload["windowId"] == 7
    bounds = payload["bounds"]
    assert bounds["windowState"] == "normal"
    assert bounds["left"] <= -10000
    assert bounds["width"] >= 1200


def test_overlay_guard_is_installed_for_current_and_future_documents():
    page = _Page()
    runtime._install_overlay_guard(page)
    assert page.init_scripts
    assert page.evaluated
    assert "stage-slideover-sidebar" in page.init_scripts[0]
    assert "pointer-events" in page.init_scripts[0]


def test_saved_project_token_is_extracted_from_project_chat_url():
    url = "https://chatgpt.com/g/g-p-6a85a9a911888191a2cc491671a4056d/c/chat-id"
    assert runtime._project_token(url) == "g-p-6a85a9a911888191a2cc491671a4056d"
