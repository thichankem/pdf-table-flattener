# Hướng Dẫn Phát Triển: PDF Table → Bullet Converter Tool

> **v5 — Cập nhật mới nhất:**
> 1. **Ollama Local trên Windows:** KHÔNG bắt buộc dùng Docker. Trên Windows có thể tải và cài đặt trực tiếp **Ollama Native** (`OllamaSetup.exe`), giúp chạy mượt mà, nhẹ tài nguyên, tận dụng GPU/CPU trực tiếp mà không cần cài Docker Desktop hay WSL2. Docker là lựa chọn tùy chọn (optional).
> 2. **Chỉ Rebuild Trang Có Bảng:** Trang KHÔNG chứa bảng sẽ được **copy nguyên bản 100%** (direct stream copy / passthrough) sang PDF kết quả mà không đụng tới bất kỳ byte hay nội dung nào. CHỈ các trang THỰC SỰ CÓ BẢNG mới được xử lý vá (patching/rebuild vùng bảng).
>
> **v4:** Kiến trúc "vá trực tiếp lên file PDF gốc" (redact + overlay bằng PyMuPDF). Mọi nội dung ngoài vùng bảng giữ nguyên.
> **v3:** Output là file PDF (không phải .md).
> **v2:** Ollama bắt buộc, tối ưu cho máy chỉ có CPU.

---

## 1. Mục Tiêu & Yêu Cầu

### 1.1 Mục tiêu chính
- Chuyển tất cả bảng trong file PDF thành dạng gạch đầu dòng (bullet points).
- **Trang không có bảng:** Copy nguyên gốc 100% (passthrough) sang file kết quả.
- **Trang có bảng:** Mọi nội dung **ngoài vùng bảng** phải giữ nguyên tuyệt đối (không đổi font, không đổi vị trí trừ trường hợp bị đẩy xuống do bảng tràn, không mất ảnh/vector).
- Output cuối cùng là **file PDF**.
- Xử lý được cả bảng đơn giản (viền rõ) lẫn bảng phức tạp (merged cell, không viền, layout lệch) nhờ vision LLM.
- Chạy trực tiếp trên Windows người dùng với **Ollama Native Windows** (tự động hoặc người dùng tải 1 click), không bắt buộc Docker.

### 1.2 Ràng buộc quan trọng (Cập nhật v5)
| Ràng buộc | Ý nghĩa thiết kế |
|---|---|
| **Chỉ rebuild trang có bảng** | Các trang KHÔNG chứa bảng được copy nguyên bản 100% (direct page passthrough). Không parse, không re-render các trang này |
| **Nội dung ngoài bảng tuyệt đối không bị đụng** | Với trang có bảng, sửa trực tiếp trên PDF gốc, chỉ động vào đúng vùng bbox của bảng |
| **Bullet có thể dài hơn vùng bảng gốc** | Cho phép đẩy nội dung phía dưới (trong cùng trang) xuống thấp hơn để nhường chỗ — nội dung giữ nguyên 100%, chỉ dịch vị trí dọc |
| **Output là PDF** | Cần font Unicode nhúng sẵn (tiếng Việt) khi vẽ đè text bullet lên trang |
| **Ollama Local (Windows Native / Docker)** | Hỗ trợ Ollama Native trực tiếp trên Windows (`OllamaSetup.exe`) giúp chạy nhanh, không tốn tài nguyên Docker. Docker chỉ là tuỳ chọn dự phòng |
| **Máy người dùng chủ yếu chỉ CPU** | Model vision nhẹ (`qwen2.5vl:3b`), timeout phù hợp với CPU |

### 1.3 Định nghĩa "xong" (Definition of Done) cho MVP
- [ ] Trang KHÔNG có bảng được copy nguyên bản 100% (so sánh hash/byte hoặc stream content trùng khớp hoàn toàn với trang gốc).
- [ ] Với trang CÓ bảng: diff nhị phân phần text ngoài bảng khớp 100% với bản gốc (kiểm bằng so khớp text extraction vùng ngoài bbox).
- [ ] Bảng chuyển thành bullet đúng nội dung, đúng định dạng `- key: value | key: value`.
- [ ] Khi bullet tràn khỏi bbox gốc, nội dung phía dưới trên cùng trang bị đẩy xuống đúng phần chênh lệch chiều cao.
- [ ] Chạy native thành công trên Windows với Ollama Windows (`ollama serve` + model `qwen2.5vl:3b`) mà không cần Docker.
- [ ] Có báo cáo chi tiết: trang nào được copy nguyên bản, trang nào có bảng và bị đẩy nội dung.

---

## 2. Kiến Trúc Tổng Thể (Cập Nhật v5)

```
┌────────────────────────────────────────────────────────────────┐
│                         INPUT: file PDF gốc                      │
└───────────────────────────────┬──────────────────────────────────┘
                                  ▼
                    ┌─────────────────────────┐
                    │   Bootstrap Ollama         │  (Check / Auto-start
                    │   (Windows Native/Docker)   │   Ollama local)
                    └────────────┬──────────────┘
                                  ▼
                    ┌─────────────────────────┐
                    │   Table Detector           │  Kiểm tra từng trang:
                    │   (Docling / pdfplumber)   │  Trang nào CÓ bảng?
                    └────────────┬──────────────┘
                                  │
         ┌────────────────────────┴────────────────────────┐
         │                                                 │
         ▼ (Trang KHÔNG có bảng)                           ▼ (Trang CÓ bảng)
┌─────────────────────────┐              ┌────────────────────────────────┐
│   Direct Page Copy      │              │        Table Router            │  rule-based trước, LLM
│   (Passthrough 100%)    │              │  (đọc NỘI DUNG bên trong bbox) │  vision khi confidence thấp
└────────┬────────────────┘              └───────┬─────────────────┬──────┘
         │                                       ▼                 ▼
         │                           ┌───────────────────┐  ┌────────────────────┐
         │                           │ Rule-based        │  │ LLM Vision         │
         │                           │ Extractor         │  │ (Ollama, bắt buộc) │
         │                           └─────────┬─────────┘  └──────────┬─────────┘
         │                                     └───────────┬───────────┘
         │                                                 ▼
         │                                   ┌──────────────────────────┐
         │                                   │      Formatter           │  rows -> bullet lines
         │                                   └────────────┬─────────────┘
         │                                                 ▼
         │                                   ┌──────────────────────────┐
         │                                   │   Layout Planner         │  đo chiều cao bullet cần,
         │                                   │                          │  tính phần chênh lệch cần đẩy
         │                                   └────────────┬─────────────┘
         │                                                 ▼
         │                                   ┌──────────────────────────┐
         │                                   │   PDF Patcher            │  redact vùng bảng cũ,
         │                                   │   (PyMuPDF/fitz)         │  vẽ đè bullet mới,
         │                                   │                          │  đẩy nội dung phía dưới
         │                                   └────────────┬─────────────┘
         │                                                 │
         └────────────────────────┬────────────────────────┘
                                  ▼
               OUTPUT: file PDF — Trang không có bảng copy nguyên gốc,
                       trang có bảng chỉ vá đúng vùng bbox + đẩy nếu tràn
                                  +
                       Báo cáo: trang copy nguyên, trang patch bảng
```

### 2.1 Nguyên tắc thiết kế cốt lõi (v5)
1. **Chỉ rebuild trang có bảng, copy nguyên các trang khác:** Các trang không chứa bảng sẽ được copy dạng stream/page gốc thông qua PyMuPDF (`insert_pdf`), giữ nguyên 100% cấu trúc PDF.
2. **Không bao giờ trích xuất-rồi-dựng-lại toàn trang:** Trên các trang có bảng, mọi nội dung ngoài bbox bảng không được đưa qua bất kỳ bước "extract → re-render" nào.
3. **Chỉ "vá" (patch) đúng vùng bảng:** Dùng kỹ thuật redact + overlay trên trang PDF gốc (PyMuPDF), giữ nguyên font nhúng, ảnh, vector ở mọi nơi khác trên trang đó.
4. **Dịch chuyển vị trí ≠ thay đổi nội dung:** Khi phải đẩy nội dung phía dưới xuống để nhường chỗ cho bullet dài, nội dung đó được di chuyển nguyên vẹn (dịch toạ độ content stream), không re-render glyph.
5. **Ollama Native trên Windows ưu tiên:** Dùng trực tiếp ứng dụng Ollama cho Windows, đơn giản hóa trải nghiệm người dùng cuối, không cần cài đặt Docker nặng nề.

---

## 3. Tech Stack (Cập Nhật v5)

| Lớp | Công nghệ | Lý do chọn |
|---|---|---|
| Ngôn ngữ | Python 3.10+ | Chuẩn cho xử lý dữ liệu & AI |
| **Ollama Engine (Local)** | **Ollama Windows Native** (`OllamaSetup.exe`) / Docker | Chạy trực tiếp trên Windows không qua Docker, tiết kiệm RAM/CPU, hỗ trợ GPU nếu có |
| **Phát hiện vị trí bảng** | **Docling** hoặc `page.find_tables()` (pdfplumber) | Chỉ tìm bbox bảng từng trang để phân loại trang có bảng / không bảng |
| **Đọc nội dung trong bbox** | Docling table structure / Camelot | Đọc cấu trúc bảng trong vùng bbox đã khoanh |
| LLM vision (cho bảng khó) | Ollama + `qwen2.5vl:3b` (chạy CPU/GPU local) | Nhẹ, chính xác cao cho vision table parsing |
| **Thao tác & Patch PDF** | **PyMuPDF (fitz)** | Thư viện mạnh nhất để copy trang passthrough (`insert_pdf`), redact vùng bảng, chèn text mới và dịch chuyển content stream |
| Font cho bullet overlay | Font TrueType Unicode nhúng sẵn (**Noto Sans**) | Đảm bảo hiển thị đầy đủ tiếng Việt có dấu |
| Đóng gói & Phân phối | **Windows Native (PyInstaller/Installer/Script)** ưu tiên, Docker Compose (tùy chọn) | Người dùng Windows chỉ cần tải 1 installer hoặc run script Python |
| API/UI | FastAPI, Gradio | Tạo giao diện đơn giản hoặc API chạy local |

---

## 4. Cấu Trúc Thư Mục Dự Án (Cập Nhật v5)

```
pdf-table-tool/
├── pyproject.toml
├── config.yaml
├── assets/
│   └── fonts/
│       └── NotoSans-Regular.ttf     # Font Unicode nhúng cho bullet overlay
├── setup_windows.bat                # Script hỗ trợ cài Ollama + Python env trên Windows
├── docker-compose.yml               # Tùy chọn (cho môi trường Docker server)
├── Dockerfile                       # Tùy chọn
│
├── src/
│   └── pdf_table_tool/
│       ├── __init__.py
│       ├── config.py
│       ├── ollama_bootstrap.py      # Tự tìm/khởi chạy Ollama Native Windows hoặc Docker
│       ├── table_detector.py        # Tìm bbox bảng & phân loại trang (trang có bảng / không bảng)
│       ├── extractors/
│       │   ├── base.py
│       │   ├── docling_extractor.py
│       │   ├── camelot_extractor.py
│       │   └── llm_vision_extractor.py
│       ├── router.py
│       ├── llm_backend.py
│       ├── formatter.py             # rows -> bullet text
│       ├── layout_planner.py        # Đo chiều cao cần, tính phần đẩy
│       ├── pdf_patcher.py           # Copy trang passthrough + redact/overlay/shift trang có bảng
│       ├── pipeline.py
│       └── logging_utils.py
│
├── api/main.py
├── ui/app.py
├── cli.py
│
├── tests/
│   ├── test_page_passthrough.py     # MỚI: kiểm tra trang không bảng copy nguyên 100%
│   ├── test_content_immutability.py # Kiểm tra nội dung ngoài bbox trang có bảng không đổi
│   ├── test_overflow_push.py        # Kiểm tra đẩy nội dung khi bullet tràn
│   └── test_end_to_end.py
│
└── docs/
    ├── WINDOWS_SETUP.md             # Hướng dẫn chạy Native trên Windows
    └── ARCHITECTURE.md
```

---

## 5. Chi Tiết Từng Module (Cập Nhật v5)

### 5.1 `table_detector.py` — Tìm bbox và phân loại trang

```python
import pdfplumber

def detect_tables_by_page(pdf_path):
    """
    Phân loại từng trang:
    - pages_with_tables: dict { page_num: [bbox1, bbox2, ...] }
    - pages_without_tables: set of page_num
    """
    pages_with_tables = {}
    pages_without_tables = set()

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            tables = page.find_tables()
            if tables:
                pages_with_tables[page_num] = [
                    {
                        "bbox": t.bbox, # (x0, top, x1, bottom)
                        "table_obj": t
                    }
                    for t in tables
                ]
            else:
                pages_without_tables.add(page_num)

    return pages_with_tables, pages_without_tables
```

### 5.2 `ollama_bootstrap.py` — Quản lý Ollama Native trên Windows

```python
import subprocess
import requests
import time
import shutil

OLLAMA_URL = "http://localhost:11434"

def ensure_ollama_running(model_name="qwen2.5vl:3b"):
    """
    Kiểm tra dịch vụ Ollama local trên Windows.
    Nếu chưa chạy, tự kích hoạt `ollama serve`.
    Nếu chưa có model, tự thực hiện `ollama pull`.
    """
    # 1. Kiểm tra xem Ollama service đã phản hồi chưa
    try:
        res = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        if res.status_code == 200:
            print("Ollama Local đã sẵn sàng.")
    except requests.RequestException:
        print("Ollama chưa khởi chạy. Đang kích hoạt Ollama Native...")
        ollama_bin = shutil.which("ollama")
        if not ollama_bin:
            raise RuntimeError(
                "Không tìm thấy Ollama trên hệ thống. "
                "Vui lòng tải và cài đặt từ https://ollama.com/download/OllamaSetup.exe"
            )
        subprocess.Popen([ollama_bin, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(3)

    # 2. Kiểm tra & pull model nếu chưa có
    res = requests.get(f"{OLLAMA_URL}/api/tags").json()
    models = [m["name"] for m in res.get("models", [])]
    if not any(model_name in m for m in models):
        print(f"Đang tự động tải model {model_name}...")
        subprocess.run(["ollama", "pull", model_name], check=True)
```

### 5.3 `pdf_patcher.py` — Rebuild trang có bảng & Copy nguyên trang không bảng

```python
import fitz  # PyMuPDF

FONT_PATH = "assets/fonts/NotoSans-Regular.ttf"

def process_pdf(pdf_path, output_path, patches_by_page, pages_without_tables):
    """
    - Trang KHÔNG có bảng: Copy nguyên bản 100% (insert_pdf).
    - Trang CÓ bảng: CHỈ redact + overlay đúng vùng bbox bảng (+ shift nếu tràn).
    """
    src_doc = fitz.open(pdf_path)
    out_doc = fitz.open()

    for page_num in range(len(src_doc)):
        if page_num in pages_without_tables:
            # COPY NGUYÊN BẢN 100%: Direct stream copy, giữ nguyên toàn bộ byte/structure
            out_doc.insert_pdf(src_doc, from_page=page_num, to_page=page_num)
        else:
            # Trang CÓ BẢNG: Tạo trang mới từ trang gốc và patch
            out_doc.insert_pdf(src_doc, from_page=page_num, to_page=page_num)
            page = out_doc[-1]  # Trang vừa chèn
            page_patches = patches_by_page.get(page_num, [])

            for patch in page_patches:
                x0, top, x1, bottom = patch["original_bbox"]
                extra = patch["extra_height"]

                if extra > 0:
                    # Dịch chuyển nội dung phía dưới bbox nếu bullet tràn
                    _shift_content_below(page, threshold_y=bottom, shift=extra)

                # Redact sạch vùng bảng cũ
                new_bottom = bottom + extra
                rect = fitz.Rect(x0, top, x1, new_bottom)
                page.add_redact_annot(rect, fill=(1, 1, 1))
                page.apply_redactions()

                # Vẽ đè bullet mới
                text = "\n".join(patch["bullet_lines"])
                page.insert_textbox(
                    rect, text,
                    fontsize=9,
                    fontfile=FONT_PATH,
                    fontname="NotoSans",
                )

    out_doc.save(output_path)
```

---

## 6. Xử Lý Tràn Nội Dung (Overflow) & Copy Trang Passthrough

### 6.1 Copy Trang Passthrough (Trang Không Có Bảng)
- Các trang không có bảng chiếm tỉ lệ lớn trong nhiều tài liệu PDF.
- Việc dùng `out_doc.insert_pdf(src_doc, from_page=p, to_page=p)` giúp copy nguyên dạng các đối tượng PDF (font, image, vector, xref table) sang file đích mà **không giải mã, không render lại**, đảm bảo tốc độ cực nhanh và khớp nhị phân 100%.

### 6.2 Dịch chuyển nội dung trên trang có bảng (khi bullet tràn)
Khi bullet cần nhiều chiều cao hơn bbox gốc: **đẩy nội dung phía dưới xuống trong cùng trang**.
Cơ chế dịch chuyển áp dụng 1 trong các phương án (ưu tiên POC Phương án C dùng Form XObject / matrix translation hoặc Phương án A với pikepdf).

---

## 7. Packaging & Distribution (Windows Native vs Docker)

### 7.1 Hướng Dẫn Chạy Windows Native (Khuyến Nghị)
1. Tải và cài đặt **Ollama cho Windows**: `https://ollama.com/download/OllamaSetup.exe`
2. Mở Terminal / PowerShell và chạy:
   ```cmd
   ollama pull qwen2.5vl:3b
   ```
3. Cài đặt Python dependencies:
   ```cmd
   pip install -r pyproject.toml
   ```
4. Kích hoạt ứng dụng:
   ```cmd
   python cli.py --input test.pdf --output result.pdf
   ```

### 7.2 Docker Compose (Tùy chọn nâng cao)
Dành cho môi trường Server hoặc Linux container. Giữ nguyên Dockerfile & `docker-compose.yml` như cấu hình v4.

---

## 8. Roadmap Phát Triển Theo Giai Đoạn (Cập Nhật v5)

### Giai đoạn 1 — Setup Windows Native & Page Passthrough POC (3 ngày)
- [ ] Xây dựng `ollama_bootstrap.py` nhận diện Ollama Native trên Windows.
- [ ] Thử nghiệm `test_page_passthrough.py` đảm bảo trang không bảng copy giữ 100% byte.
- [ ] POC dịch chuyển content stream cho trang có bảng (mục 6.2).

### Giai đoạn 2 — Detector & Page Classifier (1 tuần)
- [ ] `table_detector.py` phân loại chính xác trang có bảng / không có bảng.
- [ ] Tích hợp Docling / Camelot đọc nội dung bảng trong bbox.

### Giai đoạn 3 — Formatter & PDF Patcher (1-2 tuần)
- [ ] `layout_planner.py` tính toán chiều cao bullet.
- [ ] `pdf_patcher.py` áp dụng redact + overlay Unicode + passthrough trang.

### Giai đoạn 4 — UI / CLI & Phân phối (3-5 ngày)
- [ ] Viết `setup_windows.bat` tự động hóa các bước cài đặt trên Windows.
- [ ] Hoàn thiện CLI / Gradio UI.

---

## 9. Testing Strategy (Cập Nhật v5)

| Loại test | Mục đích |
|---|---|
| **`test_page_passthrough.py`** | Xác nhận trang KHÔNG bảng được copy nguyên bản 100%, không bị sửa đổi hay re-render |
| **`test_content_immutability.py`** | Xác nhận vùng NẰM NGOÀI bbox bảng ở trang CÓ bảng không bị đổi font/chữ |
| **`test_overflow_push.py`** | Kiểm tra đẩy nội dung phía dưới khi bullet tràn bbox |
| **Test Ollama Windows Native** | Đảm bảo phần mềm kết nối & chạy mượt mà với Ollama cài trên Windows |

---

## 10. Checklist Trước Khi Release

- [ ] Chạy thành công trên Windows sạch chỉ cần tải `OllamaSetup.exe` (không cài Docker).
- [ ] Trang KHÔNG có bảng passthrough 100% nhanh chóng & chính xác.
- [ ] Dấu tiếng Việt hiển thị sắc nét, đúng font Noto Sans.
- [ ] Báo cáo tổng kết liệt kê danh sách trang copy nguyên vs trang patch bảng.