"""Expose production selectors/parser to the headless Chromium regression."""
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def selector(path, function):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == function)
    return next(n.args[0].value for n in ast.walk(node)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "evaluate" and isinstance(n.args[0], ast.Constant))


if __name__ == "__main__":
    request = json.load(sys.stdin)
    if request["op"] == "selectors":
        result = {
            "content": selector("app/additions/chatgpt_content_response_runtime.py", "_conversation_candidates"),
            "image": selector("app/additions/chatgpt_playwright_image.py", "_candidate_is_after_marker"),
        }
    else:
        from app.additions.chatgpt_json_recovery_runtime import extract_json
        result = extract_json(request["text"], request["product"])
    print(json.dumps(result, ensure_ascii=True))
