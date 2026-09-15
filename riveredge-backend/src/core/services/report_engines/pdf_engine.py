"""
PDF报表生成引擎模块

统一使用 Playwright Chromium 生成 PDF（与业务打印同源，依赖 optional pdf extra）。
"""

from typing import Dict, Any
from io import BytesIO
from loguru import logger

from core.services.pdf.playwright_engine import run_playwright_with_dedicated_loop


class PDFEngine:
    """
    PDF报表生成引擎

    使用 Playwright 将 HTML 转为 PDF。
    """

    def generate(self, config: Dict[str, Any], data: Dict[str, Any]) -> BytesIO:
        """
        生成PDF报表

        Args:
            config: 报表配置
            data: 报表数据

        Returns:
            BytesIO: PDF文件流

        """
        html_content = self._generate_html(config, data)
        try:
            pdf_bytes = run_playwright_with_dedicated_loop(html_content)
        except RuntimeError as exc:
            logger.error("Playwright PDF 生成失败: {}", exc)
            raise
        output = BytesIO(pdf_bytes)
        output.seek(0)
        return output

    def _generate_html(self, config: Dict[str, Any], data: Dict[str, Any]) -> str:
        """
        生成HTML内容

        Args:
            config: 报表配置
            data: 数据

        Returns:
            str: HTML内容
        """
        components = config.get("components", [])

        html_parts = [
            "<!DOCTYPE html>",
            "<html>",
            "<head>",
            "<meta charset='UTF-8'>",
            "<style>",
            "@page { size: A4 portrait; margin: 12mm; }",
            "body { font-family: 'Microsoft YaHei', Arial, sans-serif; padding: 20px; }",
            "table { border-collapse: collapse; width: 100%; margin: 10px 0; }",
            "th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }",
            "th { background-color: #4472C4; color: white; }",
            "h1, h2, h3 { margin: 10px 0; }",
            "</style>",
            "</head>",
            "<body>",
        ]

        for component in components:
            html_parts.append(self._render_component_html(component, data))

        html_parts.extend([
            "</body>",
            "</html>",
        ])

        return "\n".join(html_parts)

    def _render_component_html(self, component: Dict[str, Any], data: Dict[str, Any]) -> str:
        """
        渲染组件HTML

        Args:
            component: 组件配置
            data: 数据

        Returns:
            str: HTML片段
        """
        component_type = component.get("type")

        if component_type == "table":
            return self._render_table_html(component, data)
        elif component_type == "text":
            return self._render_text_html(component)
        elif component_type == "chart":
            logger.warning("PDF图表渲染暂未实现")
            return "<div>图表组件（暂未实现）</div>"
        elif component_type == "image":
            return self._render_image_html(component)
        else:
            return ""

    def _render_table_html(self, component: Dict[str, Any], data: Dict[str, Any]) -> str:
        """
        渲染表格HTML

        Args:
            component: 组件配置
            data: 数据

        Returns:
            str: HTML片段
        """
        table_data = data.get(component.get("data_source", ""), [])
        columns = component.get("columns", [])

        html_parts = ["<table>", "<thead>", "<tr>"]

        for col in columns:
            html_parts.append(f"<th>{col.get('title', col.get('dataIndex', ''))}</th>")

        html_parts.extend(["</tr>", "</thead>", "<tbody>"])

        for row_data in table_data:
            html_parts.append("<tr>")
            for col in columns:
                data_index = col.get("dataIndex", "")
                value = row_data.get(data_index, "")
                html_parts.append(f"<td>{value}</td>")
            html_parts.append("</tr>")

        html_parts.extend(["</tbody>", "</table>"])

        return "\n".join(html_parts)

    def _render_text_html(self, component: Dict[str, Any]) -> str:
        """
        渲染文本HTML

        Args:
            component: 组件配置

        Returns:
            str: HTML片段
        """
        content = component.get("content", "")
        text_type = component.get("textType", "paragraph")

        if text_type == "title":
            level = component.get("level", 1)
            return f"<h{level}>{content}</h{level}>"
        elif text_type == "label":
            return f"<strong>{content}</strong>"
        else:
            return f"<p>{content}</p>"

    def _render_image_html(self, component: Dict[str, Any]) -> str:
        """
        渲染图片HTML

        Args:
            component: 组件配置

        Returns:
            str: HTML片段
        """
        src = component.get("src", "")
        alt = component.get("alt", "")
        return f'<img src="{src}" alt="{alt}" style="max-width: 100%;" />'
