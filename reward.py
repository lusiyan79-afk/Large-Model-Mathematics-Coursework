import math
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, Iterable, List, Optional, Tuple


GRAPHIC_TAGS = {
    "path",
    "circle",
    "rect",
    "ellipse",
    "line",
    "polyline",
    "polygon",
    "text",
}

ALLOWED_TAGS = GRAPHIC_TAGS | {
    "svg",
    "defs",
    "g",
    "lineargradient",
    "radialgradient",
    "stop",
    "clippath",
    "mask",
    "title",
    "desc",
}

UNSAFE_TAGS = {
    "script",
    "foreignobject",
    "iframe",
    "embed",
    "object",
    "image",
    "audio",
    "video",
    "canvas",
}

COLOR_NAMES = {
    "black",
    "white",
    "red",
    "blue",
    "green",
    "yellow",
    "orange",
    "purple",
    "pink",
    "brown",
    "gray",
    "grey",
    "cyan",
    "magenta",
    "navy",
    "teal",
    "lime",
    "maroon",
    "silver",
    "gold",
}

THEME_TERMS = {
    "circle",
    "square",
    "triangle",
    "star",
    "shield",
    "leaf",
    "tree",
    "flower",
    "mountain",
    "wave",
    "sun",
    "moon",
    "cloud",
    "bird",
    "fish",
    "book",
    "code",
    "data",
    "robot",
    "rocket",
    "camera",
    "music",
    "medical",
    "health",
    "coffee",
    "food",
    "sport",
    "game",
    "school",
    "travel",
    "energy",
    "security",
    "finance",
}

STOP_WORDS = {
    "about",
    "above",
    "after",
    "again",
    "against",
    "also",
    "and",
    "around",
    "brand",
    "clean",
    "color",
    "design",
    "detailed",
    "draw",
    "for",
    "from",
    "icon",
    "into",
    "logo",
    "modern",
    "simple",
    "style",
    "that",
    "the",
    "this",
    "using",
    "with",
}

HEX_COLOR_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")
FUNC_COLOR_RE = re.compile(r"\b(?:rgb|rgba|hsl|hsla)\([^)]*\)", re.IGNORECASE)
WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_-]{2,}")
NUMBER_RE = re.compile(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?")
EVENT_ATTR_RE = re.compile(r"^on[a-z]+$", re.IGNORECASE)
URL_ATTR_RE = re.compile(r"\b(?:javascript:|data:|https?://)", re.IGNORECASE)
ELEMENT_SNIPPET_RE = re.compile(
    r"<(?:path|circle|rect|ellipse|line|polyline|polygon)\b[^>]{0,180}>",
    re.IGNORECASE,
)


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("content", "text", "output", "svg"):
            if key in value:
                return _to_text(value[key])
    return str(value)


def _looks_like_svg(value: Any) -> bool:
    text = _to_text(value).lower()
    return "<svg" in text or "</svg>" in text


def _split_args(first: Any, second: Any = None) -> Tuple[str, Optional[str]]:
    first_text = _to_text(first)
    second_text = _to_text(second)
    if second is None:
        return first_text, None
    first_is_svg = _looks_like_svg(first_text)
    second_is_svg = _looks_like_svg(second_text)
    if second_is_svg and not first_is_svg:
        return second_text, first_text
    return first_text, second_text


def _extract_svg(text: str) -> Tuple[str, Dict[str, bool]]:
    lowered = text.lower()
    start = lowered.find("<svg")
    end = lowered.rfind("</svg>")
    meta = {
        "has_svg_open": start >= 0,
        "has_svg_close": end >= 0,
        "has_prefix": start > 0,
        "has_suffix": False,
    }
    if start < 0:
        return "", meta
    if end < 0:
        return text[start:].strip(), meta
    end += len("</svg>")
    meta["has_suffix"] = bool(text[end:].strip())
    return text[start:end].strip(), meta


def _local_name(tag: str) -> str:
    if "}" in tag:
        tag = tag.rsplit("}", 1)[1]
    return tag.lower()


def _numbers(value: str) -> List[float]:
    nums = []
    for item in NUMBER_RE.findall(value or ""):
        try:
            num = float(item)
        except ValueError:
            continue
        if math.isfinite(num):
            nums.append(num)
    return nums


def _parse_viewbox(value: Optional[str]) -> Optional[Tuple[float, float, float, float]]:
    nums = _numbers(value or "")
    if len(nums) != 4:
        return None
    return nums[0], nums[1], nums[2], nums[3]


def _iter_graphic_elements(root: ET.Element) -> Iterable[ET.Element]:
    for elem in root.iter():
        if _local_name(elem.tag) in GRAPHIC_TAGS:
            yield elem


def _extract_colors(svg: str, root: Optional[ET.Element]) -> List[str]:
    found = set(m.group(0).lower() for m in HEX_COLOR_RE.finditer(svg))
    found.update(m.group(0).lower() for m in FUNC_COLOR_RE.finditer(svg))
    for word in WORD_RE.findall(svg.lower()):
        if word in COLOR_NAMES:
            found.add(word)
    if root is not None:
        for elem in root.iter():
            for attr in ("fill", "stroke", "stop-color"):
                value = elem.attrib.get(attr, "").strip().lower()
                if value and value not in {"none", "transparent", "currentcolor"}:
                    found.add(value)
    return sorted(found)


def _count_score(count: int) -> float:
    if count <= 0:
        return 0.0
    if count == 1:
        return 0.45
    if count == 2:
        return 0.75
    if 3 <= count <= 50:
        return 1.0
    if count <= 90:
        return 0.75
    if count <= 150:
        return 0.4
    return 0.15


def _color_score(color_count: int) -> float:
    if color_count <= 0:
        return 0.2
    if color_count == 1:
        return 0.65
    if 2 <= color_count <= 10:
        return 1.0
    if color_count <= 18:
        return 0.75
    if color_count <= 28:
        return 0.45
    return 0.2


def _viewbox_score(viewbox: Optional[Tuple[float, float, float, float]]) -> float:
    if viewbox is None:
        return 0.0
    x, y, width, height = viewbox
    if width <= 0 or height <= 0:
        return 0.0
    if abs(x) <= 32 and abs(y) <= 32 and 128 <= width <= 512 and 128 <= height <= 512:
        return 1.0
    if width <= 1024 and height <= 1024:
        return 0.6
    return 0.25


def _coordinate_score(root: Optional[ET.Element]) -> float:
    if root is None:
        return 0.0

    checked = 0
    good = 0
    severe = 0
    coord_attrs = {"x", "y", "x1", "y1", "x2", "y2", "cx", "cy"}
    size_attrs = {"r", "rx", "ry", "width", "height"}

    for elem in root.iter():
        for key, value in elem.attrib.items():
            key = _local_name(key)
            nums = _numbers(value)
            if not nums:
                continue
            if key in coord_attrs or key in {"points", "d"}:
                low, high = (-128, 384) if key == "d" else (-64, 320)
                for num in nums:
                    checked += 1
                    if low <= num <= high:
                        good += 1
                    if abs(num) > 2000:
                        severe += 1
            elif key in size_attrs:
                for num in nums:
                    checked += 1
                    if 0 <= num <= 384:
                        good += 1
                    if num < -10 or num > 2000:
                        severe += 1

    if checked == 0:
        return 0.4
    ratio = good / checked
    severe_ratio = severe / checked
    if ratio >= 0.98:
        score = 1.0
    elif ratio >= 0.9:
        score = 0.8
    elif ratio >= 0.75:
        score = 0.5
    else:
        score = 0.2
    if severe_ratio > 0.15:
        score *= 0.4
    elif severe_ratio > 0.03:
        score *= 0.75
    return score


def _tag_safety_score(root: Optional[ET.Element]) -> float:
    if root is None:
        return 0.0

    tags = []
    unsafe = 0
    unknown = 0
    unsafe_attrs = 0
    for elem in root.iter():
        tag = _local_name(elem.tag)
        tags.append(tag)
        if tag in UNSAFE_TAGS:
            unsafe += 1
        if tag not in ALLOWED_TAGS:
            unknown += 1
        for key, value in elem.attrib.items():
            key = _local_name(key)
            value = value or ""
            if EVENT_ATTR_RE.match(key) or URL_ATTR_RE.search(value):
                unsafe_attrs += 1

    if not tags:
        return 0.0
    score = 1.0
    score -= min(0.65, unsafe * 0.25)
    score -= min(0.35, unknown / max(1, len(tags)))
    score -= min(0.45, unsafe_attrs * 0.15)
    return max(0.0, min(1.0, score))


def _path_closure_score(root: Optional[ET.Element]) -> float:
    if root is None:
        return 0.0

    filled_paths = []
    for elem in root.iter():
        if _local_name(elem.tag) != "path":
            continue
        d = elem.attrib.get("d", "").strip()
        if not d:
            continue
        fill = elem.attrib.get("fill", "").strip().lower()
        stroke = elem.attrib.get("stroke", "").strip().lower()
        # Filled paths should normally close. Stroke-only marks can remain open.
        if fill and fill not in {"none", "transparent"}:
            filled_paths.append(d)
        elif not stroke:
            filled_paths.append(d)

    if not filled_paths:
        return 0.75

    closed = 0
    for d in filled_paths:
        stripped = re.sub(r"\s+", "", d).lower()
        if stripped.endswith("z"):
            closed += 1
    return closed / len(filled_paths)


def _degeneracy_score(full_text: str, svg: str) -> float:
    if not svg:
        return 0.0

    score = 1.0
    lower_full = full_text.lower()
    lower_svg = svg.lower()
    length = len(svg)

    if length < 80:
        score -= 0.5
    elif length < 180:
        score -= 0.2
    elif length > 9000:
        score -= 0.35
    elif length > 6500:
        score -= 0.15

    if lower_full.count("<svg") > 1:
        score -= 0.25
    if "```" in full_text:
        score -= 0.15
    if "<script" in lower_svg or "<foreignobject" in lower_svg or "<image" in lower_svg:
        score -= 0.25
    if "lorem ipsum" in lower_svg or "placeholder" in lower_svg:
        score -= 0.2

    words = WORD_RE.findall(lower_svg)
    if len(words) >= 25:
        most_common = max(words.count(word) for word in set(words))
        if most_common / len(words) > 0.35:
            score -= 0.2

    snippets = [re.sub(r"\s+", " ", item.strip().lower()) for item in ELEMENT_SNIPPET_RE.findall(svg)]
    if len(snippets) >= 8:
        most_common_snippet = max(snippets.count(item) for item in set(snippets))
        repeated_ratio = most_common_snippet / len(snippets)
        if most_common_snippet >= 8 or repeated_ratio >= 0.45:
            score -= 0.35
        elif most_common_snippet >= 5 or repeated_ratio >= 0.3:
            score -= 0.18

    return max(0.0, min(1.0, score))


def _prompt_score(prompt: Optional[str], svg: str) -> float:
    if not prompt:
        return 0.5

    prompt_words = {
        word
        for word in WORD_RE.findall(prompt.lower())
        if len(word) >= 4 and word not in STOP_WORDS
    }
    if not prompt_words:
        return 0.5

    selected = {
        word
        for word in prompt_words
        if word in THEME_TERMS or word in COLOR_NAMES
    }
    if not selected:
        selected = set(sorted(prompt_words, key=len, reverse=True)[:8])

    svg_words = set(WORD_RE.findall(svg.lower()))
    hits = len(selected & svg_words)
    if not selected:
        return 0.5
    return max(0.0, min(1.0, hits / len(selected)))


def score_svg(svg: Any, prompt: Optional[Any] = None, return_details: bool = False) -> Any:
    """Score one generated SVG logo.

    The score is a proxy metric in [0, 1]. It rewards valid, closed, simple SVG
    logos and gives only a small weight to prompt keyword overlap.
    """
    full_text = _to_text(svg)
    prompt_text = _to_text(prompt) if prompt is not None else None
    extracted, meta = _extract_svg(full_text)

    details: Dict[str, Any] = {
        "has_svg_open": meta["has_svg_open"],
        "has_svg_close": meta["has_svg_close"],
        "xml_valid": False,
        "root_is_svg": False,
        "viewbox_score": 0.0,
        "graphic_element_count": 0,
        "graphic_element_score": 0.0,
        "color_count": 0,
        "color_score": 0.0,
        "coordinate_score": 0.0,
        "tag_safety_score": 0.0,
        "path_closure_score": 0.0,
        "degeneracy_score": 0.0,
        "prompt_score": 0.0,
    }

    root = None
    if extracted:
        try:
            root = ET.fromstring(extracted)
            details["xml_valid"] = True
            details["root_is_svg"] = _local_name(root.tag) == "svg"
        except ET.ParseError:
            root = None

    structure = 0.0
    structure += 0.20 if meta["has_svg_open"] else 0.0
    structure += 0.20 if meta["has_svg_close"] else 0.0
    structure += 0.30 if details["xml_valid"] else 0.0
    structure += 0.15 if details["root_is_svg"] else 0.0

    if root is not None:
        viewbox = _parse_viewbox(root.attrib.get("viewBox") or root.attrib.get("viewbox"))
        details["viewbox_score"] = _viewbox_score(viewbox)
        structure += 0.15 * details["viewbox_score"]

        graphic_elements = list(_iter_graphic_elements(root))
        details["graphic_element_count"] = len(graphic_elements)
        details["graphic_element_score"] = _count_score(len(graphic_elements))

        colors = _extract_colors(extracted, root)
        details["color_count"] = len(colors)
        details["color_score"] = _color_score(len(colors))
        details["coordinate_score"] = _coordinate_score(root)
        details["tag_safety_score"] = _tag_safety_score(root)
        details["path_closure_score"] = _path_closure_score(root)
    else:
        details["color_count"] = len(_extract_colors(extracted, None))
        details["color_score"] = _color_score(details["color_count"])

    details["degeneracy_score"] = _degeneracy_score(full_text, extracted)
    details["prompt_score"] = _prompt_score(prompt_text, extracted)

    suffix_penalty = 0.04 if meta["has_prefix"] or meta["has_suffix"] else 0.0
    score = (
        0.30 * structure
        + 0.17 * details["graphic_element_score"]
        + 0.12 * details["color_score"]
        + 0.12 * details["coordinate_score"]
        + 0.09 * details["tag_safety_score"]
        + 0.06 * details["path_closure_score"]
        + 0.09 * details["degeneracy_score"]
        + 0.05 * details["prompt_score"]
        - suffix_penalty
    )
    if details["graphic_element_count"] == 0:
        score = min(score, 0.35)
    if details["viewbox_score"] == 0.0 and details["root_is_svg"]:
        score = min(score, 0.65)
    score = max(0.0, min(1.0, score))
    details["score"] = score

    if return_details:
        return details
    return score


def reward(first: Any, second: Any = None, **_: Any) -> float:
    """Compatibility wrapper for either reward(svg, prompt) or reward(prompt, svg)."""
    svg, prompt = _split_args(first, second)
    return float(score_svg(svg, prompt))


def compute_reward(prompt: Any, completion: Any, **kwargs: Any) -> float:
    return reward(prompt, completion, **kwargs)


def score(first: Any, second: Any = None, **kwargs: Any) -> float:
    return reward(first, second, **kwargs)


def batch_reward(prompts: Iterable[Any], completions: Iterable[Any]) -> List[float]:
    return [compute_reward(prompt, completion) for prompt, completion in zip(prompts, completions)]


if __name__ == "__main__":
    good_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">'
        '<circle cx="128" cy="128" r="80" fill="#1B3A5C"/>'
        '<path d="M80 140 L128 72 L176 140 Z" fill="#FFFFFF"/>'
        "</svg>"
    )
    bad_svg = "<svg><circle cx='9999'"
    print("good", score_svg(good_svg, "blue mountain circle logo", True))
    print("bad", score_svg(bad_svg, "blue mountain circle logo", True))
