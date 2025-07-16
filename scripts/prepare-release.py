#!/usr/bin/env python3
"""Remove tool.uv.sources from pyproject.toml for release."""
import re

with open('pyproject.toml', 'r') as f:
    content = f.read()

# Remove [tool.uv.sources] section
content = re.sub(r'\[tool\.uv\.sources\].*?(?=\[|$)', '', content, flags=re.DOTALL)

# Clean up extra newlines
content = re.sub(r'\n{3,}', '\n\n', content)

with open('pyproject.toml', 'w') as f:
    f.write(content)

print("✓ Removed tool.uv.sources section for release")
