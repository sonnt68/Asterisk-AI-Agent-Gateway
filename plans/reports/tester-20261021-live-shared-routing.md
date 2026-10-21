# Kiểm thử Call Routing trên server — 2026-10-21

## Kết luận

Đã triển khai Call Routing: mỗi số có một app nhận cuộc gọi vào và có thể gán
nhiều app dùng số đó để gọi ra. Định tuyến và Caller ID qua Gateway đúng cả bốn
số. Âm thanh qua SIP trunk chưa ổn định: lượt kiểm tra cuối đạt hai trong bốn
cuộc; hai cuộc còn lại bị Asterisk đóng AudioSocket ngay sau khi trả lời.

## Bằng chứng

- Bộ kiểm thử local: Python tập trung 61; toàn bộ 234; Node SDK 24; build UI qua.
- Thử nội bộ: bốn DID đến đúng app đang được gán và có PCM; tám cuộc gọi echo
  từ hai app thử, mỗi app dùng cả bốn số, đều đúng Caller ID và có PCM.
- Các cuộc gọi dưới đây đi qua hai kênh PJSIP của trunk đang cấu hình. Tất cả
  đều trả lời, đến đúng app nhận số đích và giữ đúng số nguồn.

| Số nguồn → số đích | App nhận số đích | Âm thanh hai chiều lượt cuối |
| --- | --- | --- |
| 842444562933 → 842444562943 | ava-voice-agent | Đạt; mỗi kênh RTP TX 50 / RX 50, mất 0 |
| 842444562943 → 842444562952 | vindynamics-2 | Lỗi `media_failed` |
| 842444562952 → 842444563065 | vindynamics-3 | Lỗi `media_failed` |
| 842444563065 → 842444562933 | vindynamics-1 | Đạt; mỗi kênh RTP TX 50 / RX 50, mất 0 |

Hai call ID lỗi lần lượt:
`8952fcb9-e47f-4789-b343-3a2b926e3a48`,
`3a3f878e-a652-4a4c-b187-a3d7ac57715a`.
Call history ghi `answered=true`, `dial_status=ANSWER`, `reason=media_failed`,
đóng sau khoảng 0.1–0.2 giây. Log Asterisk cùng UUID ghi
`Failed to read header from AudioSocket because: Resource temporarily unavailable`
và `Failed to receive frame from AudioSocket server`.

[Mã nguồn Asterisk 21.10.2](https://github.com/asterisk/asterisk/blob/21.10.2/res/res_audiosocket.c#L262-L266)
đọc header một lần và trả lỗi khi `read()` trả `-1`, phù hợp lỗi EAGAIN đã quan
sát trên socket nonblocking. Chưa thay module hay nâng cấp Asterisk; chưa xác
nhận bản phát hành sửa lỗi phù hợp. Kết quả là lỗi media ngắt quãng, không phải
bằng chứng hai số bị nhà mạng từ chối.

## Dữ liệu và dọn dẹp

Bốn app nhận cuộc gọi vào được giữ nguyên:
842444562933 → vindynamics-1; 842444562943 → ava-voice-agent;
842444562952 → vindynamics-2; 842444563065 → vindynamics-3.
Tất cả số vẫn enabled/applied. Không tự gán quyền gọi ra cho app thật.

Đã gỡ toàn bộ gán số thử, thu hồi 24 khóa tạm, vô hiệu hóa tám app thử và đóng
các phiên thử. Sau cùng có 0 cuộc gọi, 0 kết nối agent; ARI/AudioSocket khỏe.
App thật cần kết nối Gateway để nhận cuộc gọi bình thường.

Backup trước nâng cấp đã phục hồi thử trên PostgreSQL riêng; dữ liệu cũ và bốn
mapping được giữ nguyên khi nâng `0005` → `0006`, không tự tạo outbound grants.
Không đổi cấu hình mạng/native PBX trong các lượt thử này.

## Phạm vi chưa kiểm tra

Chưa gọi từ điện thoại/mạng di động bên ngoài; chưa đo chất lượng cuộc gọi dài.
Docker chưa publish dải RTP được cấu hình trên Asterisk; đây là ranh giới cần
kiểm tra với điện thoại ngoài, chưa chứng minh là nguyên nhân của lượt gọi vòng
bị lỗi vì các cuộc đạt vẫn có RTP hai chiều đầy đủ.

Raw JSON và ảnh: `/tmp/gateway-telephony-proof-20261021/` trên máy làm việc.
Script: [live-shared-routing-probe.py](../../tests/e2e/asterisk/live-shared-routing-probe.py).
