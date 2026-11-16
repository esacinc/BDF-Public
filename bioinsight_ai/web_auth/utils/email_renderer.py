# /web_auth/utils/email_renderer.py
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))

def render_email(template_name: str, **kwargs) -> str:
    template = env.get_template(template_name)
    return template.render(**kwargs)
