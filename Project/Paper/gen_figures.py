# -*- coding: utf-8 -*-
"""Generisanje dijagrama i grafikona (ćirilica) za Master_rad_po_sablonu.docx.

Pokretanje:  python gen_figures.py   (iz Project/Paper)
Slike se upisuju u Project/Paper/figures/.
"""
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'figures')
os.makedirs(OUT, exist_ok=True)

# paleta (validirana): uni/multi/rel/ext + ekspertska
C_UNI, C_MULTI, C_REL, C_EXT = '#3B7DD8', '#2E9E8F', '#D9A441', '#D96D4F'
C_EXPERT = '#8B7FC7'
C_TEAL_D, C_TEAL_L = '#1F6E62', '#7FB3A9'
INK, MUT = '#1F2430', '#5A6270'

plt.rcParams.update({
    'font.family': 'DejaVu Sans',
    'font.size': 12,
    'axes.edgecolor': MUT,
    'axes.labelcolor': INK,
    'text.color': INK,
    'xtick.color': INK,
    'ytick.color': INK,
    'figure.facecolor': 'white',
    'axes.facecolor': 'white',
    'svg.fonttype': 'none',
})


def save(fig, name):
    fig.savefig(os.path.join(OUT, name), dpi=200, bbox_inches='tight',
                facecolor='white')
    plt.close(fig)
    print('OK', name)


def rbox(ax, x, y, w, h, fc, ec, lw=1.4):
    p = FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.012',
                       fc=fc, ec=ec, lw=lw, mutation_aspect=1.0)
    ax.add_patch(p)
    return p


# ---------------------------------------------------------------- 1. SOLO stepenice
def fig_solo():
    fig, ax = plt.subplots(figsize=(12.5, 6.8))
    ax.set_xlim(0, 12.5); ax.set_ylim(0, 7); ax.axis('off')
    levels = [
        (0.2, 0.4, 2.85, 3.1, C_UNI, '1. Униструктурални',
         'Разуме један аспект\nтеме; одговара на\nједну чињеницу.',
         'глаголи: именуј,\nдефиниши, препознај', '„Шта је процес?"'),
        (3.25, 0.4, 2.85, 4.0, C_MULTI, '2. Мулти-\nструктурални',
         'Разуме више\nаспеката, али их\nне повезује.',
         'глаголи: наброј,\nопиши, наведи', '„Наведи стања\nпроцеса."'),
        (6.3, 0.4, 2.85, 4.9, C_REL, '3. Релациони',
         'Повезује делове у\nцелину; објашњава\nодносе и узроке.',
         'глаголи: упореди,\nобјасни, анализирај', '„Како mutex\nспречава трку?"'),
        (9.35, 0.4, 2.85, 5.8, C_EXT, '4. Проширено\nапстрактни',
         'Уопштава и примењује\nзнање у новом\nконтексту.',
         'глаголи: примени,\nосмисли, предвиди', '„Реши застој у дистри-\nбуираном систему."'),
    ]
    for x, y, w, h, c, title, desc, verbs, ex in levels:
        rbox(ax, x, y, w, h, 'white', c, 1.8)
        two = '\n' in title
        hh = 1.05 if two else 0.78
        rbox(ax, x, y + h - hh, w, hh, c, c)
        ax.text(x + w/2, y + h - hh/2, title, ha='center', va='center',
                fontsize=11, fontweight='bold', color='white')
        ax.text(x + w/2, y + h - hh - 0.72, desc, ha='center', va='center',
                fontsize=9.6, color=INK)
        ax.text(x + w/2, y + 0.98, verbs, ha='center', va='center',
                fontsize=8.8, style='italic', color=c)
        ax.text(x + w/2, y + 0.42, ex, ha='center', va='center',
                fontsize=8.8, color=MUT)
    ax.annotate('', xy=(12.3, 6.75), xytext=(0.25, 6.75),
                arrowprops=dict(arrowstyle='-|>', lw=2.2, color=MUT))
    ax.text(0.25, 6.45, 'пораст когнитивне сложености', fontsize=11.5,
            style='italic', color=MUT, ha='left')
    save(fig, 'fig_solo.png')


# ---------------------------------------------------------------- 2. tok obrade
def fig_tok():
    fig, ax = plt.subplots(figsize=(13.2, 2.6))
    ax.set_xlim(0, 13.2); ax.set_ylim(0, 2.6); ax.axis('off')
    steps = [
        ('PDF\nматеријал', '#DCE9F9', C_UNI),
        ('Рашчлањивање\n(LLM)', '#DCE9F9', C_UNI),
        ('Хијерархија:\nкурс/лекција/\nсекција/објекат', '#DDF0EC', C_MULTI),
        ('Онтологија\n(везе појмова)', '#DDF0EC', C_MULTI),
        ('Генерисање\nпо СОЛО\nнивоима', '#F8ECD4', C_REL),
        ('Слој контроле\nквалитета\n(12 провера)', '#F7E0D7', C_EXT),
        ('Провера\nзнања', '#EAEAEA', MUT),
    ]
    w, h, gap = 1.72, 1.5, 0.16
    x = 0.1
    for i, (t, fc, ec) in enumerate(steps):
        rbox(ax, x, 0.55, w, h, fc, ec, 1.6)
        ax.text(x + w/2, 0.55 + h/2, t, ha='center', va='center', fontsize=10.2)
        if i < len(steps) - 1:
            ax.annotate('', xy=(x + w + gap, 1.3), xytext=(x + w + 0.02, 1.3),
                        arrowprops=dict(arrowstyle='-|>', lw=1.8, color=MUT))
        x += w + gap + 0.02
    save(fig, 'fig_tok.png')


# ---------------------------------------------------------------- 3. arhitektura
def fig_arhitektura():
    fig, ax = plt.subplots(figsize=(11.5, 6.6))
    ax.set_xlim(0, 11.5); ax.set_ylim(0, 6.6); ax.axis('off')

    # klijentski sloj
    rbox(ax, 0.4, 5.05, 6.9, 1.25, '#DCE9F9', C_UNI, 1.8)
    ax.text(0.7, 5.98, 'Кориснички слој — React апликација', fontsize=11.5,
            fontweight='bold', color=INK, ha='left')
    for i, t in enumerate(['курсеви и\nлекције', 'преглед\nсадржаја', 'генерисање\nпитања',
                           'банка питања\nи провере', 'контролна табла\nквалитета']):
        rbox(ax, 0.62 + i*1.32, 5.16, 1.2, 0.62, 'white', C_UNI, 1.0)
        ax.text(0.62 + i*1.32 + 0.6, 5.47, t, ha='center', va='center', fontsize=7.4)

    # serverski sloj
    rbox(ax, 0.4, 2.5, 6.9, 2.05, '#DDF0EC', C_MULTI, 1.8)
    ax.text(0.7, 4.25, 'Серверски слој — Flask (Python), REST API', fontsize=11.5,
            fontweight='bold', color=INK, ha='left')
    srv = ['рашчлањивање\nматеријала', 'генератор\nпитања', 'менаџер\nонтологије',
           'сервиси\nпровере (12)', 'преводилац', 'SPARQL\nсервис']
    for i, t in enumerate(srv):
        rbox(ax, 0.62 + (i % 3)*2.2, 3.42 - (i // 3)*0.82, 2.0, 0.66, 'white', C_MULTI, 1.0)
        ax.text(0.62 + (i % 3)*2.2 + 1.0, 3.75 - (i // 3)*0.82, t,
                ha='center', va='center', fontsize=8.6)

    # sloj podataka
    rbox(ax, 0.4, 0.35, 6.9, 1.55, '#F8ECD4', C_REL, 1.8)
    ax.text(0.7, 1.62, 'Слој података', fontsize=11.5, fontweight='bold', ha='left')
    rbox(ax, 0.62, 0.55, 3.1, 0.8, 'white', C_REL, 1.0)
    ax.text(2.17, 0.95, 'релациона база података\nSQLite', ha='center', va='center', fontsize=9)
    rbox(ax, 3.95, 0.55, 3.1, 0.8, 'white', C_REL, 1.0)
    ax.text(5.5, 0.95, 'онтологија (RDF/OWL)\nграф знања', ha='center', va='center', fontsize=9)

    # LLM sloj desno
    rbox(ax, 8.0, 2.5, 3.1, 3.8, '#F7E0D7', C_EXT, 1.8)
    ax.text(9.55, 5.95, 'Слој језичког\nмодела', fontsize=11.5, fontweight='bold',
            ha='center', va='center')
    rbox(ax, 8.25, 4.35, 2.6, 0.95, 'white', C_EXT, 1.0)
    ax.text(9.55, 4.83, 'апстракција\nпровајдера', ha='center', va='center', fontsize=9)
    rbox(ax, 8.25, 3.3, 2.6, 0.8, 'white', C_EXT, 1.0)
    ax.text(9.55, 3.7, 'Anthropic API\n(Claude Haiku 4.5)', ha='center', va='center', fontsize=8.6)
    rbox(ax, 8.25, 2.65, 2.6, 0.5, 'white', C_EXT, 1.0)
    ax.text(9.55, 2.9, 'Ollama (локални модел)', ha='center', va='center', fontsize=8.2)
    rbox(ax, 8.0, 0.9, 3.1, 1.15, '#EAEAEA', MUT, 1.4)
    ax.text(9.55, 1.47, 'кеш одговора\nмодела и провера', ha='center', va='center', fontsize=9)

    # strelice
    ax.annotate('', xy=(3.85, 5.0), xytext=(3.85, 4.6),
                arrowprops=dict(arrowstyle='<|-|>', lw=1.8, color=MUT))
    ax.text(4.0, 4.8, 'HTTP/JSON', fontsize=8.6, color=MUT)
    ax.annotate('', xy=(3.85, 2.45), xytext=(3.85, 1.95),
                arrowprops=dict(arrowstyle='<|-|>', lw=1.8, color=MUT))
    ax.annotate('', xy=(7.95, 4.0), xytext=(7.35, 4.0),
                arrowprops=dict(arrowstyle='<|-|>', lw=1.8, color=MUT))
    ax.text(7.38, 4.15, 'позиви\nмодела', fontsize=8.2, color=MUT, ha='left', va='bottom')
    ax.annotate('', xy=(9.55, 2.6), xytext=(9.55, 2.1),
                arrowprops=dict(arrowstyle='<|-|>', lw=1.6, color=MUT))
    save(fig, 'fig_arhitektura.png')


# ---------------------------------------------------------------- 4. hijerarhija
def fig_hijerarhija():
    fig, ax = plt.subplots(figsize=(11.5, 6.2))
    ax.set_xlim(0, 11.5); ax.set_ylim(0, 6.2); ax.axis('off')

    def node(x, y, w, h, t, c, fs=10.5, fc=None):
        rbox(ax, x, y, w, h, fc or 'white', c, 1.6)
        ax.text(x + w/2, y + h/2, t, ha='center', va='center', fontsize=fs)

    node(4.35, 5.3, 2.8, 0.7, 'Курс', C_UNI, 12, '#DCE9F9')
    node(1.15, 4.0, 2.6, 0.65, 'Лекција 1', C_UNI)
    node(4.45, 4.0, 2.6, 0.65, 'Лекција 2', C_UNI)
    node(7.75, 4.0, 2.6, 0.65, 'Лекција n', C_UNI)
    node(0.55, 2.7, 2.35, 0.6, 'Секција 1.1', C_MULTI)
    node(3.15, 2.7, 2.35, 0.6, 'Секција 1.2', C_MULTI)
    node(6.1, 2.7, 2.35, 0.6, 'Секција 2.1', C_MULTI)
    node(8.75, 2.7, 2.35, 0.6, 'Секција n.m', C_MULTI)
    for i, x in enumerate([0.35, 2.05, 3.75, 5.45, 7.15, 8.85]):
        node(x, 1.25, 1.55, 0.85, 'наставни\nобјекат', C_REL, 8.6)
    # strelice hijerarhije
    for x0, y0, x1, y1 in [(5.75, 5.28, 2.45, 4.67), (5.75, 5.28, 5.75, 4.67), (5.75, 5.28, 9.05, 4.67),
                           (2.45, 3.98, 1.72, 3.32), (2.45, 3.98, 4.32, 3.32),
                           (5.75, 3.98, 7.27, 3.32), (9.05, 3.98, 9.92, 3.32),
                           (1.72, 2.68, 1.12, 2.12), (1.72, 2.68, 2.82, 2.12),
                           (4.32, 2.68, 4.52, 2.12), (7.27, 2.68, 6.22, 2.12),
                           (7.27, 2.68, 7.92, 2.12), (9.92, 2.68, 9.62, 2.12)]:
        ax.annotate('', xy=(x1, y1), xytext=(x0, y0),
                    arrowprops=dict(arrowstyle='-|>', lw=1.3, color=MUT))
    # ontološke veze između LO
    for (x0, x1, lab) in [(1.9, 3.75, 'предуслов'), (5.55, 7.1, 'односи се на'),
                          (7.3, 8.85, 'део целине')]:
        ax.annotate('', xy=(x1 + 0.15, 1.18), xytext=(x0 + 0.15, 1.18),
                    arrowprops=dict(arrowstyle='-|>', lw=1.5, color=C_EXT,
                                    connectionstyle='arc3,rad=-0.35'))
        ax.text((x0 + x1)/2 + 0.15, 0.52, lab, ha='center', fontsize=8.6,
                color=C_EXT, style='italic')
    ax.text(0.3, 0.18, 'онтолошке везе између наставних објеката',
            fontsize=9.5, color=C_EXT, style='italic', ha='left')
    save(fig, 'fig_hijerarhija.png')


# ---------------------------------------------------------------- 5. LLM tok
def fig_llm():
    fig, ax = plt.subplots(figsize=(12.6, 3.4))
    ax.set_xlim(0, 12.6); ax.set_ylim(0, 3.4); ax.axis('off')
    steps = [
        ('улазни текст\n(прим. промпт)', '#DCE9F9', C_UNI),
        ('токенизација\n(деоба на\nтокене)', '#DCE9F9', C_UNI),
        ('уградње\n(вектори\nтокена)', '#DDF0EC', C_MULTI),
        ('трансформер:\nслојеви\nсамопажње', '#DDF0EC', C_MULTI),
        ('расподела\nвероватноћа\nследећег токена', '#F8ECD4', C_REL),
        ('изабрани\nтокен', '#F8ECD4', C_REL),
        ('излазни\nтекст', '#EAEAEA', MUT),
    ]
    w, h, gap = 1.64, 1.35, 0.14
    x = 0.1
    for i, (t, fc, ec) in enumerate(steps):
        rbox(ax, x, 1.35, w, h, fc, ec, 1.6)
        ax.text(x + w/2, 1.35 + h/2, t, ha='center', va='center', fontsize=9.6)
        if i < len(steps) - 1:
            ax.annotate('', xy=(x + w + gap, 2.02), xytext=(x + w + 0.02, 2.02),
                        arrowprops=dict(arrowstyle='-|>', lw=1.7, color=MUT))
        x += w + gap + 0.02
    # autoregresivna petlja
    ax.annotate('', xy=(3.9, 1.28), xytext=(10.55, 1.28),
                arrowprops=dict(arrowstyle='-|>', lw=1.5, color=C_EXT,
                                connectionstyle='arc3,rad=0.22'))
    ax.text(7.2, 0.28, 'ауторегресивна петља: изабрани токен постаје део улаза',
            ha='center', fontsize=9.6, color=C_EXT, style='italic')
    save(fig, 'fig_llm.png')


# ---------------------------------------------------------------- 6. raspodela
def fig_raspodela():
    fig, ax = plt.subplots(figsize=(9.8, 5.4))
    lessons = ['Процеси', 'Нити', 'Конкурентност']
    uni, multi, rel, ext = [40, 31, 40], [27, 18, 30], [18, 12, 20], [5, 5, 0]
    import numpy as np
    x = np.arange(3)
    bw = 0.55
    b = np.zeros(3)
    for vals, c, lab in [(uni, C_UNI, 'униструктурална'), (multi, C_MULTI, 'мултиструктурална'),
                         (rel, C_REL, 'релациона'), (ext, C_EXT, 'проширено апстрактна')]:
        ax.bar(x, vals, bw, bottom=b, color=c, label=lab,
               edgecolor='white', linewidth=2)
        b += np.array(vals)
    for i, tot in enumerate(b):
        ax.text(x[i], tot + 1.6, str(int(tot)), ha='center', fontsize=13,
                fontweight='bold')
    ax.set_xticks(x); ax.set_xticklabels(lessons, fontsize=12.5)
    ax.set_ylabel('број питања', fontsize=12)
    ax.set_ylim(0, 100)
    ax.spines[['top', 'right']].set_visible(False)
    ax.yaxis.grid(True, color='#E8E8E8', lw=0.8); ax.set_axisbelow(True)
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.08), ncol=2,
              frameon=False, fontsize=10.5)
    save(fig, 'fig_raspodela.png')


# ---------------------------------------------------------------- 7. CoVe kontekst
def fig_cove():
    import numpy as np
    fig, ax = plt.subplots(figsize=(9.8, 5.2))
    lessons = ['Процеси', 'Нити', 'Конкурентност']
    minimal = [38.9, 59.2, 41.1]
    wide = [54.4, 67.6, 64.2]
    x = np.arange(3); bw = 0.34
    ax.bar(x - bw/2 - 0.015, minimal, bw, color=C_TEAL_L,
           label='минимални контекст (само цитат)', edgecolor='white', lw=1)
    ax.bar(x + bw/2 + 0.015, wide, bw, color=C_TEAL_D,
           label='шири контекст (цитат + наставни објекат)', edgecolor='white', lw=1)
    for i in range(3):
        ax.text(x[i] - bw/2 - 0.015, minimal[i] + 1.2, f'{minimal[i]:.1f}%'.replace('.', ','),
                ha='center', fontsize=10.5)
        ax.text(x[i] + bw/2 + 0.015, wide[i] + 1.2, f'{wide[i]:.1f}%'.replace('.', ','),
                ha='center', fontsize=10.5, fontweight='bold')
        d = wide[i] - minimal[i]
        dlab = ('+%.1f' % d).replace('.', ',') + ' п.п.'
        ax.text(x[i] + bw/2 + 0.015, wide[i] + 5.4, dlab,
                ha='center', fontsize=9, color=C_TEAL_D)
    ax.set_xticks(x); ax.set_xticklabels(lessons, fontsize=12.5)
    ax.set_ylabel('удео потврђених одговора (%)', fontsize=11.5)
    ax.set_ylim(0, 82)
    ax.spines[['top', 'right']].set_visible(False)
    ax.yaxis.grid(True, color='#E8E8E8', lw=0.8); ax.set_axisbelow(True)
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.08), ncol=2,
              frameon=False, fontsize=10)
    save(fig, 'fig_cove.png')


# ---------------------------------------------------------------- 8/9. poređenja
def _poredjenje(name, ours, expert, ours_label):
    import numpy as np
    metrics = ['Решивост\n(×100)', 'Решивост из\nтекста (%)', 'Ланац провере\nпотврђено (%)',
               'Уверљивост\nдистр. (×20)', 'Јасноћа\n(100 − двосм.)', 'Грам.\nуједнач. (%)',
               'Haladyna\n(0–100)']
    fig, ax = plt.subplots(figsize=(11.8, 5.6))
    x = np.arange(len(metrics)); bw = 0.36
    ax.bar(x - bw/2 - 0.015, ours, bw, color=C_MULTI, label=ours_label,
           edgecolor='white', lw=1)
    ax.bar(x + bw/2 + 0.015, expert, bw, color=C_EXPERT,
           label='експертска питања (EduQG)', edgecolor='white', lw=1)
    for i in range(len(metrics)):
        ax.text(x[i] - bw/2 - 0.015, ours[i] + 1.2, f'{ours[i]:g}'.replace('.', ','),
                ha='center', fontsize=10)
        ax.text(x[i] + bw/2 + 0.015, expert[i] + 1.2, f'{expert[i]:g}'.replace('.', ','),
                ha='center', fontsize=10)
    ax.set_xticks(x); ax.set_xticklabels(metrics, fontsize=9.8)
    ax.set_ylabel('вредност (више је боље)', fontsize=11.5)
    ax.set_ylim(0, 112)
    ax.spines[['top', 'right']].set_visible(False)
    ax.yaxis.grid(True, color='#E8E8E8', lw=0.8); ax.set_axisbelow(True)
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.1), ncol=2,
              frameon=False, fontsize=10.5)
    save(fig, name)


def fig_poredjenja():
    # prosek tri lekcije OS (rešivost 91.9→92; stem 61.1; cove 62.1; face 3.59*20=71.8→72;
    # jasnoća 95.1; gram 95.4; haladyna 95.6)
    _poredjenje('fig_os_vs_ekspertska.png',
                [92, 61.1, 62.1, 71.8, 95.1, 95.4, 95.6],
                [94, 45.3, 64.7, 78.4, 75.2, 95.3, 93.5],
                'наша питања (просек три лекције ОС)')
    # pilot lekcija iz EduQG pasusa (rešivost 94.4→94; stem 58; cove 61; face 3.55*20=71;
    # jasnoća 92; gram 100; haladyna 94.2)
    _poredjenje('fig_pilot_vs_ekspertska.png',
                [94.4, 58, 61, 71, 92, 100, 94.2],
                [94, 45.3, 64.7, 78.4, 75.2, 95.3, 93.5],
                'наша питања из EduQG пасуса (пилот)')


# ---------------------------------------------------------------- 10. kalibracija
def fig_kalibracija():
    import numpy as np
    checks = ['Haladyna правила (грешка)', 'уверљивост дистрактора',
              'решивост (p < 0,5)', 'граматичка уједначеност',
              'двосмисленост', 'ланац провере (шири контекст)',
              'ланац провере (минимални)']
    vals = [0.0, 0.7, 4.7, 4.7, 24.8, 35.6, 42.3]
    colors = [C_MULTI, C_MULTI, C_MULTI, C_MULTI, C_REL, C_EXT, C_EXT]
    fig, ax = plt.subplots(figsize=(10.6, 4.6))
    y = np.arange(len(checks))
    ax.barh(y, vals, 0.6, color=colors, edgecolor='white', lw=1)
    for i, v in enumerate(vals):
        ax.text(v + 0.7, y[i], f'{v:.1f}%'.replace('.', ','), va='center', fontsize=10.5)
    ax.set_yticks(y); ax.set_yticklabels(checks, fontsize=10.5)
    ax.invert_yaxis()
    ax.set_xlabel('удео експертских питања означених као проблематична (ниже је боље)',
                  fontsize=10.5)
    ax.set_xlim(0, 50)
    ax.spines[['top', 'right']].set_visible(False)
    ax.xaxis.grid(True, color='#E8E8E8', lw=0.8); ax.set_axisbelow(True)
    save(fig, 'fig_kalibracija.png')


if __name__ == '__main__':
    fig_solo()
    fig_tok()
    fig_arhitektura()
    fig_hijerarhija()
    fig_llm()
    fig_raspodela()
    fig_cove()
    fig_poredjenja()
    fig_kalibracija()
    print('DONE')
