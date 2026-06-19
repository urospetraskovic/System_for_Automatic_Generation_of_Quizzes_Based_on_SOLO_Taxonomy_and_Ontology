# -*- coding: utf-8 -*-
"""Generiše grafike i dijagrame za master rad iz izmerenih podataka."""
import os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'figures')
os.makedirs(OUT, exist_ok=True)

plt.rcParams.update({
    'font.family': 'DejaVu Sans',
    'font.size': 11,
    'axes.edgecolor': '#444444',
    'axes.linewidth': 0.8,
    'figure.dpi': 200,
})
LOCAL = '#d08a4a'   # lokalni model (qwen)
GLOBAL = '#2a9d8f'  # globalni model (Haiku)
GOLD = '#8e7cc3'
GREY = '#9aa0a6'
LESSONS = ['Procesi', 'Niti', 'Konkurentnost']


def save(fig, name):
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, name), bbox_inches='tight')
    plt.close(fig)
    print('  ->', name)


# --- Fig 1: lokalni vs globalni, ključne mere (više = bolje), prosek po lekcijama ---
def fig_local_global():
    metrics = ['SOLO kapa\n(×100)', 'CoVe\npotvrđeno', 'Rešivost iz\nteksta', 'IOC\n(×100)',
               'Jasnoća\n(100-dvosm.)', 'Gram.\nujednač.']
    loc = [51.3, 14.4, 0.0, -1.0, 49.2, 66.9]
    glob = [74.7, 46.4, 61.1, 65.7, 95.1, 90.0]
    x = np.arange(len(metrics)); w = 0.38
    fig, ax = plt.subplots(figsize=(9, 4.6))
    b1 = ax.bar(x - w/2, loc, w, label='Lokalni model (Qwen 2.5 14B)', color=LOCAL)
    b2 = ax.bar(x + w/2, glob, w, label='Globalni model (Claude Haiku 4.5)', color=GLOBAL)
    ax.set_ylabel('Vrednost (više je bolje)')
    ax.set_title('Kvalitet po sloju provera: lokalni vs globalni model\n(prosek tri lekcije)',
                 fontweight='bold')
    ax.set_xticks(x); ax.set_xticklabels(metrics)
    ax.legend(frameon=False, loc='upper left')
    ax.set_ylim(-8, 108)
    ax.axhline(0, color='#999', lw=0.7)
    ax.grid(axis='y', alpha=0.25)
    for b in list(b1) + list(b2):
        h = b.get_height()
        ax.annotate(f'{h:.0f}', (b.get_x()+b.get_width()/2, h + (1.5 if h >= 0 else -5)),
                    ha='center', fontsize=8.5, color='#333')
    save(fig, 'fig1_local_global.png')


# --- Fig 2: CoVe potvrđeno po lekciji (lokalni / globalni / posle popravke) ---
def fig_cove():
    loc = [10.0, 14.3, 18.8]
    glob = [38.9, 59.2, 41.1]
    postfix = [54.4, None, None]
    x = np.arange(3); w = 0.27
    fig, ax = plt.subplots(figsize=(8, 4.4))
    ax.bar(x - w, loc, w, label='Lokalni', color=LOCAL)
    ax.bar(x, glob, w, label='Globalni', color=GLOBAL)
    ax.bar(x + w, [p if p else 0 for p in postfix], w,
           label='Globalni + širi kontekst (popravka)', color='#1d6f64')
    ax.annotate('54,4%', (0 + w, 54.4 + 1.5), ha='center', fontsize=9, fontweight='bold')
    ax.annotate('+15,5 p.p.', (0 + w, 30), ha='center', fontsize=8, color='#1d6f64')
    for i, v in enumerate(loc): ax.annotate(f'{v:.0f}%', (i - w, v + 1.5), ha='center', fontsize=8.5)
    for i, v in enumerate(glob): ax.annotate(f'{v:.0f}%', (i, v + 1.5), ha='center', fontsize=8.5)
    ax.set_xticks(x); ax.set_xticklabels(LESSONS)
    ax.set_ylabel('Udeo potvrđenih pitanja (CoVe)')
    ax.set_title('Lanac provere: udeo potvrđenih odgovora po lekciji', fontweight='bold')
    ax.legend(frameon=False, fontsize=9)
    ax.set_ylim(0, 70); ax.grid(axis='y', alpha=0.25)
    save(fig, 'fig2_cove.png')


# --- Fig 3: radar lokalni vs globalni ---
def fig_radar():
    labels = ['SOLO kapa', 'CoVe', 'Rešivost\niz teksta', 'IOC', 'Jasnoća', 'Gram.\nujednač.']
    loc = [51.3, 14.4, 0.0, 49.5, 49.2, 66.9]   # IOC mapiran (-1..1)->(0..100): (-0.01+1)/2*100
    glob = [74.7, 46.4, 61.1, 82.9, 95.1, 90.0]
    N = len(labels)
    ang = np.linspace(0, 2*np.pi, N, endpoint=False).tolist()
    ang += ang[:1]
    loc += loc[:1]; glob += glob[:1]
    fig, ax = plt.subplots(figsize=(6.2, 6.2), subplot_kw=dict(polar=True))
    ax.set_theta_offset(np.pi/2); ax.set_theta_direction(-1)
    ax.set_xticks(ang[:-1]); ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylim(0, 100); ax.set_yticks([25, 50, 75, 100])
    ax.set_yticklabels(['25', '50', '75', '100'], fontsize=8, color='#777')
    ax.plot(ang, loc, color=LOCAL, lw=2, label='Lokalni'); ax.fill(ang, loc, color=LOCAL, alpha=0.2)
    ax.plot(ang, glob, color=GLOBAL, lw=2, label='Globalni'); ax.fill(ang, glob, color=GLOBAL, alpha=0.2)
    ax.set_title('Profil kvaliteta: lokalni vs globalni model', fontweight='bold', pad=20)
    ax.legend(loc='upper right', bbox_to_anchor=(1.2, 1.1), frameon=False)
    save(fig, 'fig3_radar.png')


# --- Fig 4: SOLO raspodela po lekciji (stacked) ---
def fig_solo():
    uni = [40, 31, 40]; multi = [27, 18, 30]; rel = [18, 12, 20]; ea = [5, 5, 0]
    x = np.arange(3)
    fig, ax = plt.subplots(figsize=(7.5, 4.4))
    c = ['#4c9be8', '#52b788', '#e9c46a', '#e76f51']
    ax.bar(x, uni, label='Unistrukturalna', color=c[0])
    ax.bar(x, multi, bottom=uni, label='Multistrukturalna', color=c[1])
    b2 = np.array(uni)+np.array(multi)
    ax.bar(x, rel, bottom=b2, label='Relaciona', color=c[2])
    b3 = b2+np.array(rel)
    ax.bar(x, ea, bottom=b3, label='Prošireno apstraktna', color=c[3])
    for i in range(3):
        tot = uni[i]+multi[i]+rel[i]+ea[i]
        ax.annotate(f'{tot}', (i, tot+1.5), ha='center', fontweight='bold', fontsize=10)
    ax.set_xticks(x); ax.set_xticklabels(LESSONS)
    ax.set_ylabel('Broj pitanja')
    ax.set_title('Raspodela generisanih pitanja po SOLO nivoima (246 ukupno)', fontweight='bold')
    ax.legend(frameon=False, fontsize=9, ncol=2, loc='upper center', bbox_to_anchor=(0.5, -0.08))
    ax.set_ylim(0, 100); ax.grid(axis='y', alpha=0.2)
    save(fig, 'fig4_solo_distribution.png')


# --- Fig 5: EduQG kalibracija (specifičnost + senzitivnost) ---
def fig_eduqg_spec():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.2), gridspec_kw={'width_ratios': [1.5, 1]})
    names = ['Haladyna\n(greška)', 'Rešivost', 'Gramatika', 'Uverljivost\ndistr.',
             'Dvosmislenost', 'Lanac provere']
    vals = [0.0, 4.7, 4.7, 0.7, 24.8, 42.3]
    colors = ['#2a9d8f' if v <= 10 else ('#e9b949' if v <= 25 else '#e05d44') for v in vals]
    y = np.arange(len(names))[::-1]
    ax1.barh(y, vals, color=colors)
    for yi, v in zip(y, vals): ax1.annotate(f'{v:.1f}%', (v+0.6, yi), va='center', fontsize=9)
    ax1.annotate('uz širi kontekst: 35,6%', (36, y[-1]), va='center', fontsize=8, color='#1d6f64')
    ax1.set_yticks(y); ax1.set_yticklabels(names, fontsize=9)
    ax1.set_xlabel('Udeo označenih stručnjačkih pitanja (niže je bolje)')
    ax1.set_title('Specifičnost provera na EduQG', fontweight='bold', fontsize=11)
    ax1.set_xlim(0, 50); ax1.grid(axis='x', alpha=0.2)
    # senzitivnost
    s_names = ['Lanac\nprovere', 'Rešivost']
    s_vals = [94.6, 98.0]
    ax2.bar([0, 1], s_vals, color=GLOBAL, width=0.55)
    for i, v in enumerate(s_vals): ax2.annotate(f'{v:.0f}%', (i, v+1), ha='center', fontsize=9)
    ax2.set_xticks([0, 1]); ax2.set_xticklabels(s_names, fontsize=9)
    ax2.set_ylim(0, 108); ax2.set_ylabel('Uhvaćeno pokvarenih (više je bolje)')
    ax2.set_title('Senzitivnost', fontweight='bold', fontsize=11)
    ax2.grid(axis='y', alpha=0.2)
    fig.suptitle('Kalibracija mernih instrumenata na referentnom skupu EduQG (149 pitanja)',
                 fontweight='bold', fontsize=12)
    save(fig, 'fig5_eduqg_calibration.png')


# --- Fig 6: EduQG distraktori ---
def fig_eduqg_distr():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9, 4))
    ax1.bar(['Naši', 'Ekspertski'], [4.07, 3.95], color=[GLOBAL, GOLD], width=0.5)
    for i, v in enumerate([4.07, 3.95]): ax1.annotate(f'{v:.2f}', (i, v+0.05), ha='center')
    ax1.set_ylim(0, 5); ax1.set_ylabel('Uverljivost (od 5)')
    ax1.set_title('Uverljivost distraktora: naši vs gold', fontweight='bold', fontsize=11)
    ax1.grid(axis='y', alpha=0.2)
    ax2.bar(['Tačno', 'Delimično'], [12.3, 19.5], color=GREY, width=0.5)
    for i, v in enumerate([12.3, 19.5]): ax2.annotate(f'{v:.1f}%', (i, v+0.5), ha='center')
    ax2.set_ylim(0, 30); ax2.set_ylabel('Udeo (%)')
    ax2.set_title('Obnova ekspertskih distraktora', fontweight='bold', fontsize=11)
    ax2.grid(axis='y', alpha=0.2)
    save(fig, 'fig6_eduqg_distractors.png')


# --- Fig 7: dijagram toka sistema ---
def fig_pipeline():
    fig, ax = plt.subplots(figsize=(11, 2.6))
    ax.axis('off'); ax.set_xlim(0, 11); ax.set_ylim(0, 2.6)
    steps = ['PDF\nmaterijal', 'Raščlanjivanje\n(LLM)',
             'Hijerarhija\nkurs/lekcija/\nsekcija/objekat', 'Ontologija\n(veze pojmova)',
             'Generisanje\npo SOLO\nnivoima', 'Sloj kontrole\nkvaliteta\n(12 provera)',
             'Kviz']
    cols = ['#cfe8ff', '#cfe8ff', '#d7f0e3', '#d7f0e3', '#fde8c8', '#f6d6d2', '#e7e7e7']
    n = len(steps); bw = 1.35; gap = (11 - n*bw) / (n+1)
    xs = []
    for i, (s, c) in enumerate(zip(steps, cols)):
        x = gap + i*(bw+gap)
        xs.append(x)
        box = FancyBboxPatch((x, 0.8), bw, 1.0, boxstyle='round,pad=0.02,rounding_size=0.08',
                             fc=c, ec='#555', lw=1.0)
        ax.add_patch(box)
        ax.text(x+bw/2, 1.3, s, ha='center', va='center', fontsize=8.2)
    for i in range(n-1):
        a = FancyArrowPatch((xs[i]+bw, 1.3), (xs[i+1], 1.3), arrowstyle='-|>',
                            mutation_scale=14, color='#555', lw=1.2)
        ax.add_patch(a)
    ax.set_title('Tok obrade: od nastavnog materijala do provere znanja', fontweight='bold')
    save(fig, 'fig7_pipeline.png')


# --- Fig 8: SOLO lestvica ---
def fig_solo_ladder():
    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    ax.axis('off'); ax.set_xlim(0, 10); ax.set_ylim(0, 5)
    levels = [('Unistrukturalni', 'jedna činjenica', '#4c9be8'),
              ('Multistrukturalni', 'više činjenica', '#52b788'),
              ('Relacioni', 'povezivanje pojmova', '#e9c46a'),
              ('Prošireno apstraktni', 'primena u novom kontekstu', '#e76f51')]
    ax.annotate('', xy=(9.6, 4.5), xytext=(0.3, 0.5),
                arrowprops=dict(arrowstyle='-|>', color='#888', lw=1.4), zorder=1)
    for i, (name, desc, c) in enumerate(levels):
        x = 0.6 + i*2.3; h = 1.0 + i*0.95
        ax.add_patch(FancyBboxPatch((x, 0.4), 2.0, h, boxstyle='round,pad=0.02,rounding_size=0.06',
                                    fc=c, ec='#555', alpha=1.0, zorder=3))
        ax.text(x+1.0, 0.4+h-0.3, name, ha='center', va='top', fontsize=9.5, fontweight='bold',
                color='white', zorder=4)
        ax.text(x+1.0, 0.4+0.28, desc, ha='center', va='bottom', fontsize=8, color='#222', zorder=4)
    ax.text(0.3, 4.7, 'porast kognitivne složenosti', fontsize=9, color='#444', style='italic')
    ax.set_title('SOLO taksonomija: četiri nivoa koja sistem generiše', fontweight='bold')
    save(fig, 'fig8_solo_ladder.png')


# --- Fig 9: toplotna mapa poboljšanja (globalni - lokalni) ---
def fig_heatmap():
    rows = ['SOLO kapa (×100)', 'CoVe %', 'Rešivost iz teksta %', 'IOC (×100)',
            'Jasnoća %', 'Gram. ujednač. %']
    data = np.array([
        [78-63, 78-64, 68-27],
        [38.9-10, 59.2-14.3, 41.1-18.8],
        [50-0, 69-0, 64.2-0],
        [69-(-1), 66-(-4), 62-2],
        [(100-4.4)-(100-52.5), (100-7)-(100-48.2), (100-3.2)-(100-51.6)],
        [92.2-68.8, 87.3-67.9, 90.5-64.1],
    ])
    fig, ax = plt.subplots(figsize=(7.5, 4.4))
    im = ax.imshow(data, cmap='Greens', aspect='auto', vmin=0, vmax=70)
    ax.set_xticks(range(3)); ax.set_xticklabels(LESSONS)
    ax.set_yticks(range(len(rows))); ax.set_yticklabels(rows, fontsize=9)
    for i in range(len(rows)):
        for j in range(3):
            ax.text(j, i, f'+{data[i,j]:.0f}', ha='center', va='center',
                    color='white' if data[i, j] > 38 else '#1a1a1a', fontsize=9, fontweight='bold')
    ax.set_title('Poboljšanje prelaskom na globalni model\n(razlika globalni minus lokalni, po lekciji)',
                 fontweight='bold', fontsize=11)
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cb.set_label('porast (procentni poeni / poeni)', fontsize=9)
    save(fig, 'fig9_improvement_heatmap.png')


# --- Fig 10: naša pitanja vs ekspertska po metrici (normalizovano, više = bolje) ---
def fig_our_vs_expert():
    metrics = ['Rešivost\n(×100)', 'CoVe\npotvrđeno', 'Uverljivost\ndistr. (×20)',
               'Jasnoća\n(100-dvosm.)', 'Gram.\nujednač.', 'Haladyna']
    ours = [92, 62, 72, 95, 95, 96]      # prosek tri lekcije
    exp = [94, 65, 78, 75, 95, 94]       # ekspertska (EduQG)
    x = np.arange(len(metrics)); w = 0.38
    fig, ax = plt.subplots(figsize=(9, 4.6))
    b1 = ax.bar(x - w/2, ours, w, label='Naša pitanja (prosek tri lekcije)', color=GLOBAL)
    b2 = ax.bar(x + w/2, exp, w, label='Ekspertska pitanja (EduQG)', color=GOLD)
    ax.set_ylabel('Vrednost (više je bolje)')
    ax.set_title('Kvalitet naših pitanja naspram ekspertskih, po metrici', fontweight='bold')
    ax.set_xticks(x); ax.set_xticklabels(metrics)
    ax.legend(frameon=False, loc='lower right')
    ax.set_ylim(0, 108)
    ax.grid(axis='y', alpha=0.25)
    for b in list(b1) + list(b2):
        h = b.get_height()
        ax.annotate(f'{h:.0f}', (b.get_x()+b.get_width()/2, h + 1.5), ha='center', fontsize=8.5, color='#333')
    save(fig, 'fig10_our_vs_expert.png')


if __name__ == '__main__':
    print('Generišem grafike u', OUT)
    fig_local_global(); fig_cove(); fig_radar(); fig_solo(); fig_eduqg_spec()
    fig_eduqg_distr(); fig_pipeline(); fig_solo_ladder(); fig_heatmap()
    fig_our_vs_expert()
    print('Gotovo.')
