# Bảng rà soát tỷ lệ sở hữu SOTP_HOLDINGS (cho phi), 20/10/2026

Nguồn số liệu: `config/sotp_holdings.yaml` (bước s5/s7/r4b). Cột thị trường đo trên snapshot DB 20/10/2026, chỉ đọc.
- **stake** là LỢI ÍCH KINH TẾ hiệu quả (trực tiếp + gián tiếp). Không phải tỷ lệ pháp lý của pháp nhân trung gian.
- **±1 điểm %**: FV mã mẹ đổi bao nhiêu khi stake đổi 1 điểm %. Công thức: 0,01 × (vốn hóa con − VCSH mẹ của
  con) / số cp mẹ × 0,9. Với EIB (ghi theo giá gốc) là 0,01 × vốn hóa / số cp mẹ × 0,9, giữ nguyên giá gốc.
  Mã nào có độ nhạy lớn thì soát trước.
- Hiện cả 5 mã mẹ đều bị chặn bởi `SOTP_HOLDINGS_UNVERIFIED`. Sau r4b, không công ty con nào còn lỗi dữ liệu
  (audit nguồn xong, 0 xung đột).

**Cách duyệt:** rà từng dòng, sửa `stake`/`source`/`source_date` nếu cần, rồi điền ở cấp mã mẹ
`reviewed_by: phi` và `as_of: YYYY-MM-DD` (ngày đối chiếu xong). TTL là 180 ngày: quá hạn thì thành
`SOTP_HOLDINGS_STALE` (bị chặn).

## VIC (FV 49.927đ, thị giá 207.000đ, không có CTCK; còn chặn thêm DOWNSIDE_EXTREME_REVIEW)
| Công ty con | stake | Nguồn | Ngày nguồn | Pháp lý vs kinh tế / cần kiểm | P/B | ±1 điểm % |
|---|---|---|---|---|---|---|
| VHM | 71,58% | https://thitruongtaichinhtiente.vn/vingroup-muon-chuyen-quyen-so-huu-hon-4-8-trieu-co-phieu-vhm-84366.html | 2026-07-20 | 2,94/4,107 tỷ cp, sở hữu trực tiếp (pháp lý = kinh tế). Cổ tức CP 100% (06/08/2026) không đổi tỷ lệ. Cần kiểm các đợt chuyển nhượng VHM sau 07/2026 (theinvestor ghi 71,07%). | 1,91 | 274đ |
| VPL | 85,5% | https://mbs.com.vn/files/uploads/2026/07/VPL12601_BCtraiphieu_20260730.pdf | 2026-07-30 | Trực tiếp. VPL đã chuyển phần lớn cp VIC cho trái chủ trong 6T26, nên sở hữu chéo coi như không đáng kể. | 3,31 | 122đ |
| VRE | 18,37% | https://doanhnhan.baophapluat.vn/co-dong-cua-vincom-retail-vre-sap-nhan-duoc-hon-2-200-ty-dong-tien-tra-co-tuc.html | 2025-12-31 | Trực tiếp. Phần gián tiếp 41,5% qua SDI đã chuyển nhượng. Nguồn là số cuối 2025. | 1,09 | 5đ |

## MSN (FV 126.062đ, thị giá 72.400đ, CTCK 93.250đ n=6, +35,2%)
| Công ty con | stake | Nguồn | Ngày nguồn | Pháp lý vs kinh tế / cần kiểm | P/B | ±1 điểm % |
|---|---|---|---|---|---|---|
| MCH | 66,0% | https://www.kbsec.com.vn/pic/Service/KBSV_MSN_Baocaocapnhat_20251215.pdf | 2025-12-15 | Lợi ích kinh tế lấy từ KBSV Bảng 15. Pháp lý khoảng 69,4% (bbw.vn, 07/10/2026), sau ESOP 1% còn khoảng 65,3%. Lepus đăng ký mua thêm tối đa 73 tr cp (09–23/10/2026): chỉ nâng stake khi BCTC đã ghi nhận. **Độ nhạy lớn nhất.** | 9,69 | 961đ |
| TCB | 19,8% | (như MCH) | 2025-12-15 | Đối chiếu bằng lãi từ TCB 2025 (4.997 tỷ) / LNST mẹ TCB (25.290 tỷ) = 19,76%. Là công ty liên kết. | 1,25 | 276đ |
| MSR (mới, Q4) | 92,89% | https://thitruongtaichinhtiente.vn/masan-hoan-tat-ban-2-von-masan-high-tech-materials-tang-ty-le-free-float-co-phieu-msr-len-7-11-82873.html | 2026-05-13 | Nắm qua CTCP Tầm nhìn Masan (100% vốn MSN), nên pháp lý trung gian = kinh tế. Free float 7,11%. **[fin_a] MÂU THUẪN SỐ HỌC ĐÃ ĐỐI CHIẾU — phi rà trước khi điền reviewed_by:** 92,89% − 4,99% = 87,90%, không phải 87,46%. Nguyên nhân là khác mẫu số: CafeF 01/10/2026 (https://cafef.vn/tap-doan-my-da-mua-xong-499-co-phan-masan-high-tech-materials-188261001114751078.chn) ghi Tầm nhìn Masan nắm ~1,02 tỷ cp ≈ 92,45% và Elmet nhận 55,14 tr cp = 4,99% → mẫu số ≈ 1.105 tr cp; còn 92,89% tính trên 1.099,83 tr cp (số cp trong DB, BCTC Q2/2026). Cả hai mốc đều là ~1.021,6 tr cp. Chênh 0,44 điểm % khớp đợt ESOP ~5,2 tr cp (0,47%, HĐQT 07/2026) — **suy luận, chưa có nguồn xác nhận ESOP đã phát hành xong**. Trạng thái: báo chí (CafeF) ghi Elmet đã khớp thoả thuận 55,14 tr cp sáng 01/10/2026 (~3.240 tỷ); Tầm nhìn Masan còn đăng ký bán thêm 5,01% cho NĐT tổ chức (01–30/10/2026) → có thể còn ~82,45%. Engine tính vốn hóa = giá × số cp DB nên stake phải **cùng mẫu số DB**: sau Elmet = 966,4 / 1.099,83 = **0,8787** (−5,02 điểm % ≈ −1.712đ); sau cả 10% = 911,08 / 1.099,83 = 0,8284 (≈ −3.430đ). Dùng 0,8746 với số cp DB hiện tại sẽ đếm thiếu ~4,5 tr cp (~140đ). Stake chưa đổi (0,9289) — phi quyết. | 5,01 | 341đ |
| MML (mới, Q4) | 94,3% | https://www.kbsec.com.vn/pic/Service/KBSV_MSN_Baocaocapnhat_20251215.pdf | 2025-12-15 | Lợi ích kinh tế lấy từ KBSV Bảng 15. Chưa có nguồn cho tỷ lệ pháp lý / pháp nhân trung gian. Cần đối chiếu thuyết minh BCTC Q2/2026 của MSN. | 1,61 | 19đ |

## GEX (FV 37.232đ, thị giá 22.750đ, CTCK 40.500đ n=1, −8,1%; mốc 28/09: +8,3%, n=2)
| Công ty con | stake | Nguồn | Ngày nguồn | Pháp lý vs kinh tế / cần kiểm | P/B | ±1 điểm % |
|---|---|---|---|---|---|---|
| GEE | 75,96% | https://www.kbsec.com.vn/pic/Service/KBSV_Baocaolandau_GEX_20260213.pdf | 2026-02-13 | KBSV ghi 76%; vnstock subsidiaries 75,96% (sau đợt bán 3% GEE trong Q4/2025). Sở hữu trực tiếp. | 5,28 | 237đ |
| GEL | 70,21% | https://tapchicongthuong.vn/tap-doan-gelex--gex-sap-tam-ung-co-tuc-tien-mat--du-kien-ipo-ha-tang-gelex-203138.htm | 2026-08-03 | Trực tiếp 624,9/890 tr cp. Chưa cộng 1,85% của Công ty TNHH Phát điện Gelex (chưa rõ thuộc GEX hay GEL). VGC là con của GEL nên không khai riêng (tránh đếm trùng). | 1,95 | 82đ |
| EIB | 10% (giá gốc 3.297 tỷ) | https://nhadautu.vn/gelex-se-tang-so-huu-tai-eximbank-len-15-khi-dieu-kien-phap-ly-cho-phep-d103973.html | (thiếu source_date) | Đầu tư tài chính ghi theo giá gốc. Tỷ lệ 10% là số cuối 2025, chưa cập nhật sau khi EIB tăng lên 1.868,8 tr cp. **Cần bổ sung source_date và tỷ lệ hiện hành.** | 1,15 | 209đ |

## REE (FV 36.679đ, thị giá 45.050đ, CTCK 61.600đ n=10, −40,5%)
Cả ba công ty con dưới đây REE nắm qua Công ty TNHH Năng lượng R.E.E, trong đó REE sở hữu 100%
(https://vnbusiness.vn/lai-tang-manh-nhung-cong-ty-thuy-dien-cua-ree-van-dung-truoc-nguy-co-bi-huy-tu-cach-dai-chung.html).
Vì vậy pháp lý trung gian = kinh tế.
| Công ty con | stake | Nguồn | Ngày nguồn | Pháp lý vs kinh tế / cần kiểm | P/B | ±1 điểm % |
|---|---|---|---|---|---|---|
| VSH | 52,58% | https://www.dnse.com.vn/senses/tin-tuc/thuy-dien-vinh-son-song-hinh-sap-tam-ung-co-tuc-bang-tien-mat-ty-le-15-35254969 | 2026-06-30 | 124,2 tr cp; vnstock/VCI 124.212.978 cp (27/07/2026). | 1,90 | 66đ |
| TBC | 60,42% | (vnbusiness ở trên) | 2025-12-31 | vnstock/VCI 38.365.168 cp (27/07/2026). | 1,73 | 12đ |
| TMP | 42,63% | https://doanhnhan.baophapluat.vn/co-dong-cua-thuy-dien-thac-mo-tmp-sap-nhan-duoc-280-ty-dong-tien-tra-co-tuc.html | 2026-06-11 | Là **công ty liên kết** (EVNGENCO2 nắm 51,9%), không phải công ty con. VCI ghi 29.843.740/70 tr cp (19/08/2026). | 1,94 | 25đ |
| (không khai) CHP 24,2%, PPC 20,74% | — | — | 06/2024, 08/2024 | Nguồn cũ hơn 2 năm; PPC đang thoái vốn. Nếu có số hiện hành có nguồn thì có thể bổ sung. | | |

## TCH (FV 7.727đ, thị giá 11.250đ, CTCK 18.850đ n=2, −59,0%; mốc 28/09: −63,0%, n=3)
| Công ty con | stake | Nguồn | Ngày nguồn | Pháp lý vs kinh tế / cần kiểm | P/B | ±1 điểm % |
|---|---|---|---|---|---|---|
| HHS | 58,31% | https://mekongasean.vn/hoa-ng-huy-tch-chot-nga-y-mua-64-trieu-co-phieu-hhs-phat-ha-nh-rieng-le-42165.html | 2025-06-02 (đã xác nhận qua VCI 13/08/2026) | 251.905.777/431,99 tr cp, trực tiếp. P/B 0,43 làm phần định giá lại âm (−3.008 tỷ). | 0,43 | −46đ |

## Ghi nhớ khi mở công bố
Mở công bố nghĩa là điền `reviewed_by` và `as_of`. Mô phỏng trong bộ nhớ ở cả hai mốc cho thấy ngay khi điền,
GEX/REE/TCH/MSN đều công bố được (không còn cờ chặn nào khác). Riêng VIC vẫn bị chặn bởi DOWNSIDE_EXTREME_REVIEW.
- REE −40,5% (n=10) và TCH −59%/−63% đã có mục registry ở trạng thái must_fix, chưa được duyệt. [fin_a] Đã đặt
  sẵn hold REE và TCH trong `config/event_holds.yaml` (since 2026-10-20, ngưỡng `publication_gate.new_listing_hold_dev`
  0,40): điền `reviewed_by` thì hai mã vẫn bị chặn `MATERIAL_EVENT_HOLD` tới khi phi duyệt mục registry rồi xoá hold.
- MSN +35,2% (mốc 20/10) là hệ quả của Q4; registry đã ghi `out_of_band_justified`, owner phi. Mức lệch chỉ vừa
  vượt band 0,35. Nếu sau này vào band ở cả hai mốc thì mục này thành OBSOLETE và phải gỡ.
