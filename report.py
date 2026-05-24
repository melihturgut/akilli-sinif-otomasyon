# PDF rapor uretimi (reportlab kullaniyor).
# Final raporu icin tek tikla yazdirilabilir cikti.
import io
import os
import time
from collections import Counter

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib import colors
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                 TableStyle, PageBreak, KeepTogether)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import VerticalBarChart

import db
from schedule_mgr import DAY_NAMES, schedule_mgr


# Font yukleme - Turkce karakter destegi icin DejaVu Sans bundle ediyoruz
# (Render Linux'unda Arial olmadigi icin sorun cikiyordu)

def _register_fonts():
    here = os.path.dirname(os.path.abspath(__file__))
    # Tercih sirasi: paketlenmis DejaVu -> Linux dejavu -> Windows arial -> Helvetica
    candidates = [
        ('TR',      os.path.join(here, 'static/fonts/DejaVuSans.ttf')),
        ('TR-Bold', os.path.join(here, 'static/fonts/DejaVuSans-Bold.ttf')),
        ('TR',      '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),
        ('TR-Bold', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'),
        ('TR',      'C:/Windows/Fonts/arial.ttf'),
        ('TR-Bold', 'C:/Windows/Fonts/arialbd.ttf'),
    ]
    base = 'Helvetica'
    bold = 'Helvetica-Bold'
    for name, path in candidates:
        if os.path.exists(path):
            try:
                # Ayni isimle ikinci kez register etme (ilk basarili oldu)
                if name == 'TR' and base != 'TR':
                    pdfmetrics.registerFont(TTFont('TR', path))
                    base = 'TR'
                elif name == 'TR-Bold' and bold != 'TR-Bold':
                    pdfmetrics.registerFont(TTFont('TR-Bold', path))
                    bold = 'TR-Bold'
            except Exception:
                pass
    return base, bold

BASE_FONT, BOLD_FONT = _register_fonts()


# --- Renkler

C_PRIMARY = colors.HexColor('#0c4a6e')
C_ACCENT  = colors.HexColor('#0284c7')
C_SUCCESS = colors.HexColor('#059669')
C_DANGER  = colors.HexColor('#dc2626')
C_WARNING = colors.HexColor('#d97706')
C_TEXT    = colors.HexColor('#0f172a')
C_MUTED   = colors.HexColor('#64748b')
C_BG      = colors.HexColor('#f1f5f9')
C_BORDER  = colors.HexColor('#cbd5e1')


def _styles():
    base = getSampleStyleSheet()
    return {
        'cover_title': ParagraphStyle('cover_title', parent=base['Title'],
            fontName=BOLD_FONT, fontSize=28, leading=34,
            textColor=C_PRIMARY, alignment=TA_CENTER, spaceAfter=8),
        'cover_sub': ParagraphStyle('cover_sub', parent=base['Normal'],
            fontName=BASE_FONT, fontSize=13, leading=18,
            textColor=C_MUTED, alignment=TA_CENTER, spaceAfter=16),
        'h1': ParagraphStyle('h1', parent=base['Heading1'],
            fontName=BOLD_FONT, fontSize=16, leading=20,
            textColor=C_PRIMARY, spaceBefore=12, spaceAfter=10,
            borderColor=C_ACCENT, borderWidth=0, borderPadding=0,
            leftIndent=0),
        'h2': ParagraphStyle('h2', parent=base['Heading2'],
            fontName=BOLD_FONT, fontSize=12, leading=15,
            textColor=C_TEXT, spaceBefore=8, spaceAfter=4),
        'normal': ParagraphStyle('normal', parent=base['Normal'],
            fontName=BASE_FONT, fontSize=10, leading=14, textColor=C_TEXT),
        'muted': ParagraphStyle('muted', parent=base['Normal'],
            fontName=BASE_FONT, fontSize=9, leading=12, textColor=C_MUTED),
        'kpi_label': ParagraphStyle('kpi_label', fontName=BASE_FONT,
            fontSize=8, leading=10, textColor=C_MUTED, alignment=TA_CENTER),
        'kpi_value': ParagraphStyle('kpi_value', fontName=BOLD_FONT,
            fontSize=20, leading=24, textColor=C_PRIMARY, alignment=TA_CENTER),
        'kpi_sub': ParagraphStyle('kpi_sub', fontName=BASE_FONT,
            fontSize=8, leading=10, textColor=C_MUTED, alignment=TA_CENTER),
    }


# --- Sayfa üst/alt çubuğu

def _header_footer(canvas_, doc):
    canvas_.saveState()
    w, h = A4

    # Üst başlık çubuğu
    canvas_.setFillColor(C_PRIMARY)
    canvas_.rect(0, h - 18*mm, w, 18*mm, fill=True, stroke=False)
    canvas_.setFillColor(colors.white)
    canvas_.setFont(BOLD_FONT, 11)
    canvas_.drawString(15*mm, h - 12*mm, "Akıllı Sınıf Otomasyonu")
    canvas_.setFont(BASE_FONT, 8)
    canvas_.drawRightString(w - 15*mm, h - 12*mm, time.strftime('%d.%m.%Y'))

    # Alt sayfa numarası
    canvas_.setStrokeColor(C_BORDER)
    canvas_.setLineWidth(0.5)
    canvas_.line(15*mm, 12*mm, w - 15*mm, 12*mm)
    canvas_.setFillColor(C_MUTED)
    canvas_.setFont(BASE_FONT, 8)
    canvas_.drawCentredString(w/2, 7*mm,
        f"Sayfa {doc.page}  ·  MDB308 Çok Disiplinli Takım Projesi  ·  Danışman: Muhammet Raşit Cesur")
    canvas_.restoreState()


# --- Yardımcılar

def _kpi_card(styles, label, value, sub=None, color=C_PRIMARY):
    """Tek KPI hücresi içeren bir tablo."""
    value_style = ParagraphStyle('kpi_v_' + label, parent=styles['kpi_value'], textColor=color)
    rows = [
        [Paragraph(label, styles['kpi_label'])],
        [Paragraph(value, value_style)],
    ]
    if sub:
        rows.append([Paragraph(sub, styles['kpi_sub'])])
    t = Table(rows, colWidths=[40*mm], rowHeights=None)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), C_BG),
        ('BOX', (0,0), (-1,-1), 0.5, C_BORDER),
        ('LEFTPADDING',   (0,0), (-1,-1), 6),
        ('RIGHTPADDING',  (0,0), (-1,-1), 6),
        ('TOPPADDING',    (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    return t


def _kpi_grid(styles, items):
    """4'lü KPI yan yana grid."""
    cells = [_kpi_card(styles, *it) for it in items]
    row = cells + [None] * (4 - len(cells))
    grid = Table([row], colWidths=[42*mm]*4)
    grid.setStyle(TableStyle([
        ('LEFTPADDING',  (0,0), (-1,-1), 2),
        ('RIGHTPADDING', (0,0), (-1,-1), 2),
        ('VALIGN',       (0,0), (-1,-1), 'TOP'),
    ]))
    return grid


def _data_table(header, rows, col_widths=None, header_color=C_PRIMARY):
    """Standart veri tablosu."""
    data = [header] + rows
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        # Başlık
        ('BACKGROUND', (0,0), (-1,0), header_color),
        ('TEXTCOLOR',  (0,0), (-1,0), colors.white),
        ('FONTNAME',   (0,0), (-1,0), BOLD_FONT),
        ('FONTSIZE',   (0,0), (-1,0), 9),
        ('ALIGN',      (0,0), (-1,0), 'CENTER'),
        ('TOPPADDING',    (0,0), (-1,0), 6),
        ('BOTTOMPADDING', (0,0), (-1,0), 6),
        # Veri
        ('FONTNAME',   (0,1), (-1,-1), BASE_FONT),
        ('FONTSIZE',   (0,1), (-1,-1), 8.5),
        ('TEXTCOLOR',  (0,1), (-1,-1), C_TEXT),
        ('TOPPADDING',    (0,1), (-1,-1), 4),
        ('BOTTOMPADDING', (0,1), (-1,-1), 4),
        # Çerçeve
        ('GRID', (0,0), (-1,-1), 0.4, C_BORDER),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        # Zebra
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, C_BG]),
    ]))
    return t


def _bar_chart(labels, values, title=None, value_color=C_SUCCESS,
               width=170*mm, height=70*mm, value_format='%.1f'):
    drawing = Drawing(width, height)
    chart = VerticalBarChart()
    chart.x = 30
    chart.y = 18
    chart.width = width - 50
    chart.height = height - 35
    chart.data = [values]
    chart.categoryAxis.categoryNames = labels
    chart.categoryAxis.labels.fontName = BASE_FONT
    chart.categoryAxis.labels.fontSize = 8
    chart.valueAxis.labels.fontName = BASE_FONT
    chart.valueAxis.labels.fontSize = 8
    chart.bars[0].fillColor = value_color
    chart.bars[0].strokeColor = None
    chart.bars.strokeColor = None
    chart.barWidth = 12
    chart.barSpacing = 1
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = max(values + [1]) * 1.15
    chart.valueAxis.gridStrokeColor = C_BORDER
    chart.valueAxis.gridStrokeWidth = 0.3
    chart.valueAxis.visibleGrid = True

    # Değerleri sütunların üzerine yaz
    chart.barLabels.fontName = BASE_FONT
    chart.barLabels.fontSize = 7
    chart.barLabels.fillColor = C_TEXT
    chart.barLabels.nudge = 6
    chart.barLabelFormat = value_format
    chart.barLabels.boxAnchor = 's'

    drawing.add(chart)
    return drawing


# --- Rapor Üretimi

def generate_full_report():
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                             leftMargin=15*mm, rightMargin=15*mm,
                             topMargin=26*mm, bottomMargin=18*mm,
                             title='Akıllı Sınıf Otomasyonu — Sistem Raporu',
                             author='MDB308 Takım Projesi',
                             subject='IoT Tabanlı Sınıf Enerji Yönetimi')
    styles = _styles()
    story = []

    # --- Veri toplama
    stats = db.attendance_stats()
    runs = db.list_energy_runs(limit=999)
    last_run = runs[0] if runs else None
    classes = schedule_mgr.list_all()
    class_stats = db.class_attendance_stats(classes)
    attendance = db.get_attendance(limit=10000)

    # ---
    # KAPAK
    # ---
    story.append(Spacer(1, 4*cm))
    story.append(Paragraph("AKILLI SINIF<br/>OTOMASYONU", styles['cover_title']))
    story.append(Paragraph("Sistem Performans &amp; Verimlilik Raporu", styles['cover_sub']))
    story.append(Spacer(1, 2*cm))

    # Bilgi kartı
    info = [
        ['Ders',          'MDB308 Çok Disiplinli Takım Projesi'],
        ['Danışman',      'Muhammet Raşit Cesur'],
        ['Rapor Tarihi',  time.strftime('%d.%m.%Y %H:%M')],
        ['Ekip',          'Melih Turgut, Samed Mete Özmen (BM)'],
        ['',              'Serkan Yıldırım, Enes Tunahan Pakelli (EEM)'],
        ['',              'Kamil Uzun, İrem Öz (END)'],
    ]
    t = Table(info, colWidths=[4*cm, 12*cm])
    t.setStyle(TableStyle([
        ('FONTNAME',  (0,0), (0,-1),  BOLD_FONT),
        ('FONTNAME',  (1,0), (1,-1),  BASE_FONT),
        ('FONTSIZE',  (0,0), (-1,-1), 10),
        ('TEXTCOLOR', (0,0), (0,-1),  C_PRIMARY),
        ('TEXTCOLOR', (1,0), (1,-1),  C_TEXT),
        ('LINEBELOW', (0,0), (-1,-1), 0.3, C_BORDER),
        ('TOPPADDING',    (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1, 3*cm))
    story.append(Paragraph(
        "Bu rapor, IoT tabanlı akıllı sınıf enerji yönetim sisteminin "
        "performans göstergelerini, yoklama analizlerini ve doluluk-tüketim "
        "korelasyonlarını sunar. Sayfa 2'de raporda kullanılan terimlerin "
        "açıklamaları bulunmaktadır.",
        styles['muted']))
    story.append(PageBreak())

    # ---
    # TERIMLER SOZLUGU
    # ---
    story.append(Paragraph("Terimler ve Tanımlar", styles['h1']))
    story.append(Paragraph(
        "Rapor boyunca kullanılan teknik terimlerin kısa açıklamaları:",
        styles['normal']))
    story.append(Spacer(1, 6*mm))

    terms = [
        ('Toplam Olay',
         'Sisteme yapılan tüm yoklama hareketleri: giriş, çıkış ve süre yenileme kayıtlarının toplamı.'),
        ('Benzersiz Öğrenci',
         'Sisteme en az bir kez giriş yapmış farklı öğrenci sayısı. Aynı öğrenci tekrar giriş yapsa bile 1 sayılır.'),
        ('Bugünkü Giriş',
         'Bugün (00:00\'dan itibaren) QR ile sınıfa giriş yapan kişi sayısı.'),
        ('Bazhat (Baseline)',
         'Otomasyon hiç olmasaydı sınıfta tüketilecek olan teorik enerji miktarı. Karşılaştırma referansı.'),
        ('Otomasyonlu Tüketim',
         'Akıllı sistemimiz aktifken gerçekleşen enerji tüketimi. Doluluk yoksa cihazlar kapatılır.'),
        ('Tasarruf (kWh)',
         'Bazhat tüketimi ile otomasyonlu tüketim arasındaki fark. Kazanılan elektrik miktarı.'),
        ('Tasarruf Yüzdesi',
         '(Bazhat − Otomasyonlu) / Bazhat × 100. Sistemin verimlilik oranı.'),
        ('Maliyet Kazancı (TL)',
         'Tasarruf edilen elektrik × birim fiyat (4.5 TL/kWh — Türkiye ortalaması).'),
        ('Karbon Azaltımı (kg CO₂)',
         'Tasarruf edilen elektrik × emisyon faktörü (0.4 kg CO₂/kWh — TR ortalaması).'),
        ('Doluluk Oranı',
         'Bir dersin gerçek katılımı / beklenen öğrenci sayısı × 100. Ders programı optimizasyonunda kullanılır.'),
        ('Beklenen Öğrenci',
         'Ders programında o derse kayıtlı / katılması beklenen öğrenci sayısı.'),
        ('Aktif Ders',
         'Hoca tarafından iptal edilmemiş, programda canlı görünen ders.'),
        ('Etüt Modu',
         'Ders saatleri dışında öğrencilerin QR ile sınıfı manuel açabildiği 1 saatlik zamanlanmış kullanım.'),
        ('Bölgesel Aydınlatma',
         'Sınıfın 3 bölgesinin (Ön, Orta, Arka) bağımsız aydınlatması. Sadece dolu bölgenin ışığı yanar.'),
        ('Hibrit PIR + Ultrasonik',
         'İki sensörün birlikte kullanımı. PIR hareketi, ultrasonik mesafeyi ölçer. Durağan öğrencilerde de doluluk algılanır.'),
        ('Kapasite Kullanım Oranı',
         'Sınıfın belirli bir zamanda toplam kapasitesine göre ne kadar dolu olduğu. Mekan yönetimi metriği.'),
    ]

    rows = [[Paragraph(f'<b>{name}</b>', styles['normal']),
             Paragraph(desc, styles['normal'])] for name, desc in terms]
    t = Table(rows, colWidths=[42*mm, 130*mm])
    t.setStyle(TableStyle([
        ('FONTNAME',   (0,0), (-1,-1), BASE_FONT),
        ('FONTSIZE',   (0,0), (-1,-1), 9),
        ('TEXTCOLOR',  (0,0), (0,-1), C_PRIMARY),
        ('LINEBELOW',  (0,0), (-1,-1), 0.3, C_BORDER),
        ('TOPPADDING',    (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BACKGROUND', (0,0), (-1,-1), colors.white),
    ]))
    story.append(t)
    story.append(PageBreak())

    # ---
    # 1. ÖZET KPI'LAR
    # ---
    story.append(Paragraph("1. Sistem Özet İstatistikleri", styles['h1']))
    story.append(Paragraph(
        f"{stats['total_events']} yoklama olayı, {stats['unique_students']} "
        f"benzersiz öğrenci ve {len(runs)} tamamlanmış simülasyon koşması üzerinden hesaplanmıştır.",
        styles['normal']))
    story.append(Spacer(1, 6*mm))

    # KPI grid 1 — Sim sonuçları
    if runs:
        cum_savings = sum(r['savings_kwh'] for r in runs)
        cum_cost    = sum(r['cost_saved_tl'] for r in runs)
        cum_carbon  = sum(r['carbon_saved_kg'] for r in runs)
        avg_pct     = sum(r['savings_pct'] for r in runs) / len(runs)
        story.append(_kpi_grid(styles, [
            ('Toplam Tasarruf',  f"{cum_savings:.1f}",  'kWh',                  C_SUCCESS),
            ('Maliyet Kazanımı', f"{cum_cost:,.0f}",    'TL',                   C_WARNING),
            ('Karbon Azaltımı',  f"{cum_carbon:.1f}",   'kg CO₂',               C_ACCENT),
            ('Ort. Tasarruf',    f"%{avg_pct:.1f}",     f"{len(runs)} koşma",   C_PRIMARY),
        ]))
        story.append(Spacer(1, 6*mm))

    # KPI grid 2 — Yoklama
    today_attendance = sum(1 for a in attendance
                            if time.strftime('%Y-%m-%d', time.localtime(a['timestamp'])) ==
                               time.strftime('%Y-%m-%d'))
    story.append(_kpi_grid(styles, [
        ('Yoklama Olayı',     f"{stats['total_events']:,}", 'toplam',      C_PRIMARY),
        ('Kayıtlı Öğrenci',   f"{stats['unique_students']}", 'benzersiz',  C_ACCENT),
        ('Bugünkü Giriş',     f"{stats['today_checkins']}",  'check-in',   C_SUCCESS),
        ('Aktif Dersler',     f"{sum(1 for c in classes if c.get('active'))}/{len(classes)}",
                                                            'haftalık',   C_WARNING),
    ]))

    story.append(PageBreak())

    # ---
    # 2. SON SİMÜLASYON DETAYI
    # ---
    story.append(Paragraph("2. Son Simülasyon Sonucu", styles['h1']))
    if last_run:
        story.append(Paragraph(
            f"<b>Tarih:</b> {last_run['finished_at'][:16]} &nbsp;&nbsp;"
            f"<b>Süre:</b> {last_run['total_minutes']} dakika (1 hafta)",
            styles['normal']))
        story.append(Spacer(1, 4*mm))

        # KPI gridi
        story.append(_kpi_grid(styles, [
            ('Bazhat Tüketim',    f"{last_run['energy_baseline']:.1f}", 'kWh',          C_DANGER),
            ('Otomasyonlu',       f"{last_run['energy_auto']:.1f}",     'kWh',          C_ACCENT),
            ('Tasarruf',          f"{last_run['savings_kwh']:.1f}",     f"%{last_run['savings_pct']}", C_SUCCESS),
            ('Maliyet Kazancı',   f"{last_run['cost_saved_tl']:.0f}",   'TL',           C_WARNING),
        ]))
        story.append(Spacer(1, 8*mm))

        # Günlük tablo + grafik
        story.append(Paragraph("Gün Bazında Tasarruf Dökümü", styles['h2']))

        daily = last_run.get('daily', [])
        if daily:
            # Tablo
            tbl_rows = []
            for d in daily:
                pct = (d['savings'] / d['baseline'] * 100) if d['baseline'] else 0
                tbl_rows.append([
                    d['day'],
                    f"{d['baseline']:.2f}",
                    f"{d['auto']:.2f}",
                    f"{d['savings']:.2f}",
                    f"%{pct:.1f}",
                ])
            story.append(_data_table(
                ['Gün', 'Bazhat (kWh)', 'Otomasyonlu (kWh)', 'Tasarruf (kWh)', 'Oran'],
                tbl_rows,
                col_widths=[25*mm, 35*mm, 40*mm, 35*mm, 25*mm],
            ))
            story.append(Spacer(1, 8*mm))

            # Bar chart
            labels = [d['day'] for d in daily]
            values = [d['savings'] for d in daily]
            story.append(_bar_chart(labels, values,
                                     value_color=C_SUCCESS,
                                     height=60*mm,
                                     value_format='%.1f'))
    else:
        story.append(Paragraph("Henüz tamamlanmış simülasyon yok.", styles['muted']))

    story.append(PageBreak())

    # ---
    # 3. DERS BAZLI DOLULUK ANALİZİ
    # ---
    story.append(Paragraph("3. Ders Bazlı Doluluk Analizi", styles['h1']))
    story.append(Paragraph(
        "Yoklama zaman damgaları ders programıyla eşleştirilerek her dersin "
        "gerçek katılım oranı hesaplanmıştır. Bu veri, rapor 2.6'daki "
        "<i>doluluk-tüketim korelasyon</i> analizinin girdisidir.",
        styles['normal']))
    story.append(Spacer(1, 6*mm))

    if class_stats:
        rows = []
        for c in class_stats:
            rows.append([
                c['class_name'][:22] + ('…' if len(c['class_name']) > 22 else ''),
                DAY_NAMES[c['day']][:3],
                c['time'],
                str(c['expected']),
                str(c['unique_students']),
                f"%{c['occupancy_rate']}",
                'Aktif' if c['active'] else 'İPTAL',
            ])
        story.append(_data_table(
            ['Ders', 'Gün', 'Saat', 'Beklenen', 'Giriş', 'Doluluk', 'Durum'],
            rows,
            col_widths=[42*mm, 12*mm, 24*mm, 18*mm, 18*mm, 18*mm, 18*mm],
        ))
        story.append(Spacer(1, 8*mm))

        # Bar chart — ders bazlı doluluk
        labels = [c['class_name'][:10] for c in class_stats]
        values = [c['occupancy_rate'] for c in class_stats]
        if any(values):
            story.append(Paragraph("Doluluk Grafiği (%)", styles['h2']))
            story.append(_bar_chart(labels, values,
                                     value_color=C_ACCENT,
                                     height=55*mm,
                                     value_format='%%%.0f'))
    else:
        story.append(Paragraph("Ders programı boş.", styles['muted']))

    story.append(PageBreak())

    # ---
    # 4. YOKLAMA ANALİZİ
    # ---
    story.append(Paragraph("4. Yoklama Analizi", styles['h1']))

    # Saat bazlı dağılım
    hour_counter = Counter()
    student_counter = Counter()
    for a in attendance:
        if a['action'] != 'giris':
            continue
        h = time.localtime(a['timestamp']).tm_hour
        hour_counter[h] += 1
        student_counter[a['student_no']] += 1

    if hour_counter:
        story.append(Paragraph("Saat Bazlı Giriş Dağılımı", styles['h2']))
        hours_sorted = sorted(hour_counter.keys())
        labels = [f"{h:02d}" for h in hours_sorted]
        values = [hour_counter[h] for h in hours_sorted]
        story.append(_bar_chart(labels, values,
                                 value_color=C_PRIMARY,
                                 height=50*mm,
                                 value_format='%.0f'))
        story.append(Spacer(1, 8*mm))

    # En aktif öğrenciler (top 10)
    if student_counter:
        story.append(Paragraph("En Aktif 10 Öğrenci", styles['h2']))
        top10 = student_counter.most_common(10)
        # İsimleri çek
        rows = []
        for sno, count in top10:
            student = db.get_student(sno)
            name = student['name'] if student and student.get('name') else '—'
            rows.append([sno, name, str(count)])
        story.append(_data_table(
            ['Öğrenci No', 'Ad Soyad', 'Giriş Sayısı'],
            rows,
            col_widths=[35*mm, 80*mm, 30*mm],
        ))

    story.append(PageBreak())

    # ---
    # 5. SİMÜLASYON KOŞMA GEÇMİŞİ
    # ---
    story.append(Paragraph("5. Simülasyon Koşma Geçmişi", styles['h1']))
    if runs:
        story.append(Paragraph(
            f"Sistem ömründe toplam {len(runs)} simülasyon koşması tamamlanmıştır. "
            "Aşağıdaki tablo en son 15 koşmayı listeler.",
            styles['normal']))
        story.append(Spacer(1, 4*mm))
        rows = []
        for r in runs[:15]:
            rows.append([
                f"#{r['id']}",
                r['finished_at'][:16],
                f"{r['energy_baseline']:.1f}",
                f"{r['energy_auto']:.1f}",
                f"{r['savings_kwh']:.1f}",
                f"%{r['savings_pct']}",
                f"{r['cost_saved_tl']:.0f}",
                f"{r['carbon_saved_kg']:.1f}",
            ])
        story.append(_data_table(
            ['#', 'Tarih', 'Bazhat', 'Oto.', 'Tasarruf', '%', 'TL', 'CO₂ kg'],
            rows,
            col_widths=[12*mm, 32*mm, 22*mm, 22*mm, 22*mm, 16*mm, 22*mm, 22*mm],
        ))
    else:
        story.append(Paragraph("Henüz simülasyon koşması yok.", styles['muted']))

    story.append(Spacer(1, 1.5*cm))

    # Kapanış notu
    story.append(Paragraph("Sonuç ve Değerlendirme", styles['h2']))
    if runs:
        avg = sum(r['savings_pct'] for r in runs) / len(runs)
        story.append(Paragraph(
            f"Sistem ortalama <b>%{avg:.1f}</b> enerji tasarrufu sağlamaktadır. "
            f"Tamamlanan {len(runs)} koşmada toplam <b>{sum(r['savings_kwh'] for r in runs):.1f} kWh</b> "
            f"enerji ve <b>{sum(r['cost_saved_tl'] for r in runs):,.0f} TL</b> maliyet kazanımı elde edilmiştir. "
            f"Bu değerler rapor 2.5'teki <i>tasarruf analizi formülü</i> ile hesaplanmaktadır.",
            styles['normal']))
    else:
        story.append(Paragraph(
            "Performans değerlendirmesi için en az bir tamamlanmış simülasyon koşması gereklidir.",
            styles['muted']))

    # PDF oluştur
    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return buf.getvalue()
