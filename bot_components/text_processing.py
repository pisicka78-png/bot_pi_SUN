import re


URL_PATTERN = re.compile(r"(https?://\S+|t\.me/\S+)")


def replace_links(source_html: str, target_link: str) -> str:
    if not source_html:
        return ""
    return URL_PATTERN.sub(target_link, source_html)
