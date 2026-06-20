"""[manifest] YAML-subset parser — extracted from engine.py.

Kept as a sibling source module for maintainability; the incubator inlines it into the
.pgn payload at build time so the shipped seed stays a single self-contained file.
"""


class Parser:
    """
    [Parser] YAML 块解析器——从内容中提取 YAML 元数据块。
    
    功能：
        - 识别 ```yaml ... ``` 代码块
        - 安全解析 YAML 内容
        - 合并多个 YAML 块
    """
    def _strip_comment(self, value):
        in_quote = None
        for i, char in enumerate(value):
            if char in ("'", '"') and (i == 0 or value[i - 1] != "\\"):
                in_quote = None if in_quote == char else char
            elif char == "#" and in_quote is None:
                return value[:i].rstrip()
        return value.strip()

    def _split_inline(self, value):
        parts = []
        current = []
        depth = 0
        quote = None
        for char in value:
            if char in ("'", '"'):
                quote = None if quote == char else char
            elif quote is None:
                if char in "[{(":
                    depth += 1
                elif char in "]})":
                    depth -= 1
                elif char == "," and depth == 0:
                    parts.append("".join(current).strip())
                    current = []
                    continue
            current.append(char)
        if current:
            parts.append("".join(current).strip())
        return parts

    def _parse_scalar(self, value):
        value = self._strip_comment(value)
        if value in ("", "|", ">"):
            return ""
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            return value[1:-1]
        lowered = value.lower()
        if lowered in ("true", "false"):
            return lowered == "true"
        if lowered in ("null", "none", "~"):
            return None
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            return [self._parse_scalar(item) for item in self._split_inline(inner)] if inner else []
        if value.startswith("{") and value.endswith("}"):
            result = {}
            inner = value[1:-1].strip()
            for item in self._split_inline(inner):
                if ":" in item:
                    key, raw = item.split(":", 1)
                    result[key.strip().strip("\"'")] = self._parse_scalar(raw.strip())
            return result
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            return value

    def _next_content_line(self, lines, start):
        for line in lines[start:]:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                return line
        return ""

    def _parse_yaml_subset(self, block):
        root = {}
        stack = [(-1, root)]
        lines = block.splitlines()

        for index, raw_line in enumerate(lines):
            if not raw_line.strip() or raw_line.lstrip().startswith("#"):
                continue
            indent = len(raw_line) - len(raw_line.lstrip(" "))
            stripped = raw_line.strip()

            while stack and indent <= stack[-1][0]:
                stack.pop()
            parent = stack[-1][1] if stack else root

            if stripped.startswith("- "):
                if not isinstance(parent, list):
                    continue
                item = stripped[2:].strip()
                if ":" in item and not item.startswith("{"):
                    key, raw_value = item.split(":", 1)
                    item_dict = {key.strip(): self._parse_scalar(raw_value.strip())}
                    parent.append(item_dict)
                    stack.append((indent, item_dict))
                else:
                    parent.append(self._parse_scalar(item))
                continue

            if ":" not in stripped or not isinstance(parent, dict):
                continue

            key, raw_value = stripped.split(":", 1)
            key = key.strip().strip("\"'")
            raw_value = raw_value.strip()
            if raw_value:
                parent[key] = self._parse_scalar(raw_value)
                continue

            next_line = self._next_content_line(lines, index + 1)
            next_stripped = next_line.strip()
            child = [] if next_stripped.startswith("- ") else {}
            parent[key] = child
            stack.append((indent, child))

        return root

    def parse(self, content):
        yaml_blocks = []
        in_block = False
        block_start = 0
        
        for i, line in enumerate(content.split('\n')):
            if line.startswith("```yaml"):
                in_block = True
                block_start = i + 1
            elif in_block and line.startswith("```"):
                yaml_blocks.append("\n".join(content.split('\n')[block_start:i]))
                in_block = False
        
        result = {}
        for block in yaml_blocks:
            try:
                data = self._parse_yaml_subset(block)
                if isinstance(data, dict):
                    result.update(data)
            except Exception:
                pass
        return result
