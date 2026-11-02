"""
OCR 兜底服务

用于 pypdf 从扫描版 PDF 抽不到文本时，或直接传入图片简历（jpg/png/jpeg）时，
通过 rapidocr-onnxruntime 执行中文 OCR 识别。

依赖（可选，未安装时静默降级）：
    pip install rapidocr-onnxruntime pymupdf pillow

- rapidocr-onnxruntime: PaddleOCR 的 ONNX 运行时版本，轻量，CPU 即可运行
- pymupdf: 将 PDF 页渲染为图像（仅在 OCR PDF 时用到）
- pillow: 图像格式处理
"""
from __future__ import annotations

import io
import os
from typing import List


_ocr_engine = None


def _get_ocr():
    """延迟加载 OCR 引擎，全局单例，首次调用时初始化（约 1-2 秒）。
    未安装依赖时返回 None，调用方需判定。"""
    global _ocr_engine
    if _ocr_engine is not None:
        return _ocr_engine
    try:
        from rapidocr_onnxruntime import RapidOCR
        _ocr_engine = RapidOCR()
    except ImportError:
        _ocr_engine = False  # 标记已尝试导入但不可用
    return _ocr_engine if _ocr_engine is not False else None


def ocr_available() -> bool:
    """OCR 依赖是否已安装可用"""
    return _get_ocr() is not None


def ocr_image_bytes(img_bytes: bytes) -> str:
    """对 PNG/JPG 等常见格式的图片字节执行 OCR，返回拼合后的纯文本。
    识别失败或无可读文字时返回空字符串（不抛异常）。"""
    ocr = _get_ocr()
    if ocr is None:
        return ""
    try:
        result, _elapsed = ocr(img_bytes)
    except Exception:
        return ""
    if not result:
        return ""
    # result 形如 [[bbox, text, score], ...]
    lines = [str(item[1]).strip() for item in result if item and len(item) >= 2]
    return "\n".join(lines).strip()


def pdf_to_images(pdf_path: str, dpi: int = 250) -> List[bytes]:
    """用 pymupdf 将 PDF 每一页渲染为 PNG 字节列表。
    失败或无依赖时返回空列表。"""
    try:
        import pymupdf as fitz  # pymupdf >= 2.0 推荐新命名空间
    except ImportError:
        try:
            import fitz  # pymupdf < 2.0 旧写法兼容
        except ImportError:
            return []
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return []
    images: List[bytes] = []
    try:
        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        for page in doc:
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            images.append(pix.tobytes("png"))
    finally:
        doc.close()
    return images


def ocr_pdf(pdf_path: str, dpi: int = 250) -> str:
    """对扫描版 PDF 执行 OCR：逐页渲染图像 → OCR → 按页拼合文本。
    任一层缺失依赖时返回空字符串，调用方走正常 pypdf 路径即可。"""
    ocr = _get_ocr()
    if ocr is None:
        return ""
    page_images = pdf_to_images(pdf_path, dpi=dpi)
    if not page_images:
        return ""
    pages_text: List[str] = []
    for i, img in enumerate(page_images, 1):
        text = ocr_image_bytes(img)
        if text:
            pages_text.append(f"[第{i}页]\n{text}")
    return "\n\n".join(pages_text).strip()
