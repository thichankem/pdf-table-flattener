# Hướng dẫn Test cho PDF Table Flattener

## Mục tiêu
Toàn bộ bảng (table) trong file PDF sẽ được chuyển thành dạng gạch đầu dòng làm phẳng, xóa bỏ hoàn toàn table, chỉ còn đoạn text.

**Ví dụ:**
```
- Tên: Nam  |  Tuổi: 25  |  Chức vụ: Dev
```

## Phạm vi
- Áp dụng cho **MỌI file PDF**, KHÔNG giới hạn cho bất kỳ file mẫu cụ thể nào.
- Tool tự động nhận diện kiểu bảng và chọn chiến lược flatten tối ưu.

## 3 Tiêu chí BẮT BUỘC để coi là test THÀNH CÔNG

Nhớ test **100% nội dung** file đã convert:

### Tiêu chí 1: Giữ nguyên nội dung ngoài bảng
- Toàn bộ nội dung không phải table (văn bản, tiêu đề, hình ảnh, sơ đồ) **KHÔNG được đụng chạm**, giữ nguyên hoàn toàn 100%.

### Tiêu chí 2: Flatten tất cả bảng
- Toàn bộ nội dung trong table được đưa ra thành dạng gạch đầu dòng.
- Ví dụ: `- Tên: Nam  |  Tuổi: 25  |  Chức vụ: Dev`
- **Không còn bất kỳ bảng nào** trong file kết quả.

### Tiêu chí 3: Sạch sẽ hoàn toàn
- Không có bất kỳ khoảng trống thừa, ký tự lạ, ký tự ẩn, hay nội dung kỳ lạ nào xuyên suốt file.
- Không có nhãn giả (Cột 1:, Cột 2:...) được tạo ra.
- Không có dòng trống liên tiếp > 1.
