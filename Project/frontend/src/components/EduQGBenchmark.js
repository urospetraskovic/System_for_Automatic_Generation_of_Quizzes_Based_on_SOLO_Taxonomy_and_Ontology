import React, { useEffect, useState, useCallback } from 'react';

import { eduqgApi } from '../api';

const TEAL = '#2a9d8f';
const GOLD = '#b08968';
const C = {
  muted: 'var(--neutral-600)',
  line: 'var(--neutral-200)',
  card: '#fff',
};

const BOOK_LABELS = {
  american_government: 'Američka vlada',
  anatomy_and_physiology: 'Anatomija i fiziologija',
  biology: 'Biologija',
  business_ethics: 'Poslovna etika',
  'business_law_i_essentials': 'Poslovno pravo',
  introduction_to_intellectual_property: 'Intelektualna svojina',
  introduction_to_sociology: 'Sociologija',
  microbiology: 'Mikrobiologija',
  'principles_of_accounting,_volume_1:_financial_accounting': 'Računovodstvo (finansijsko)',
  'principles_of_accounting,_volume_2:_managerial_accounting': 'Računovodstvo (menadžersko)',
  psychology: 'Psihologija',
  'u.s._history': 'Istorija SAD',
};
const bookLabel = (b) => BOOK_LABELS[b] || (b || '').replace(/_/g, ' ');

// ---------- formatiranje vrednosti po tipu metrike ----------
function fmtValue(v, fmt) {
  if (v === null || v === undefined) return 'n/a';
  switch (fmt) {
    case 'pct': return `${Number(v).toFixed(1)}%`;
    case 'p': return Number(v).toFixed(2);
    case 'score5': return `${Number(v).toFixed(2)} / 5`;
    case 'score100': return `${Number(v).toFixed(1)} / 100`;
    case 'grade': return Number(v).toFixed(1);
    case 'kappa': return Number(v).toFixed(2);
    default: return String(v);
  }
}
// širina trake u procentima (0..100) za dati tip
function barWidth(v, fmt) {
  if (v === null || v === undefined) return 0;
  let w;
  switch (fmt) {
    case 'p': w = v * 100; break;
    case 'score5': w = (v / 5) * 100; break;
    case 'grade': w = (v / 25) * 100; break;
    case 'kappa': w = ((v + 1) / 2) * 100; break;
    default: w = v; // pct, score100
  }
  return Math.max(0, Math.min(100, w));
}

function Bar({ label, value, fmt, color }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
      <div style={{ width: 120, fontSize: '0.8rem', color: C.muted, textAlign: 'right' }}>{label}</div>
      <div style={{ flex: 1, background: 'var(--neutral-100)', borderRadius: 6, height: 20, position: 'relative' }}>
        <div style={{
          width: `${barWidth(value, fmt)}%`, background: color, height: '100%',
          borderRadius: 6, transition: 'width .4s',
        }} />
      </div>
      <div style={{ width: 70, fontSize: '0.82rem', fontWeight: 600, color: 'var(--neutral-800)' }}>
        {fmtValue(value, fmt)}
      </div>
    </div>
  );
}

function MetricCard({ m }) {
  const [open, setOpen] = useState(false);
  const dirText = m.higher === true ? 'više je bolje'
    : m.higher === false ? 'niže je bolje' : 'informativno';
  return (
    <div style={{ background: C.card, border: `1px solid ${C.line}`, borderRadius: 12, padding: 16, marginBottom: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', flexWrap: 'wrap', gap: 6 }}>
        <div style={{ fontWeight: 700, color: 'var(--neutral-800)' }}>{m.name}</div>
        <div style={{ fontSize: '0.74rem', color: C.muted }}>{dirText}
          {!m.comparable && ' · samo naša pitanja'}</div>
      </div>
      <button onClick={() => setOpen(!open)} style={{
        marginTop: 4, fontSize: '0.78rem', color: '#2563eb', background: 'none',
        border: 'none', cursor: 'pointer', padding: 0,
      }}>{open ? '▾ sakrij objašnjenje' : '▸ šta ovo meri?'}</button>
      {open && <div style={{ fontSize: '0.84rem', color: C.muted, margin: '6px 0 4px', lineHeight: 1.5 }}>{m.expl}</div>}

      <div style={{ marginTop: 12 }}>
        {m.my.map((L) => (
          <Bar key={L.name} label={L.name.replace(/^\d+\s*-\s*/, '')}
               value={L.computed ? L.value : null} fmt={m.fmt} color={TEAL} />
        ))}
        {m.comparable && (
          <>
            <div style={{ borderTop: `1px dashed ${C.line}`, margin: '8px 0' }} />
            <Bar label="Ekspertska (EduQG)" value={m.expert} fmt={m.fmt} color={GOLD} />
          </>
        )}
      </div>
    </div>
  );
}

// ---------- pregled pitanja po oblasti ----------
function evalBadges(result) {
  if (!result) return null;
  const items = [];
  const push = (label, tone) => items.push({ label, tone });
  const t = { good: { bg: '#d1fae5', fg: '#166534' }, warn: { bg: '#fef3c7', fg: '#92400e' },
    bad: { bg: '#fee2e2', fg: '#991b1b' }, n: { bg: 'var(--neutral-100)', fg: 'var(--neutral-600)' } };
  push(`Lint ${result.lint.error ? 'greška' : 'ok'}`, result.lint.error ? 'bad' : 'good');
  push(result.ambiguity.ambiguous ? 'Dvosmisleno' : 'Jasno', result.ambiguity.ambiguous ? 'bad' : 'good');
  if (result.face.score != null) push(`Uverljivost ${result.face.score.toFixed(1)}`, result.face.score >= 3 ? 'good' : 'warn');
  if (result.cove.verdict) {
    const v = result.cove.verdict;
    push(`CoVe: ${v === 'SUPPORTED' ? 'potvrđeno' : v === 'CONTRADICTED' ? 'oboreno' : 'neodređeno'}`,
      v === 'SUPPORTED' ? 'good' : v === 'CONTRADICTED' ? 'bad' : 'warn');
  }
  if (result.solvability.p_value != null) push(`Rešivost p=${result.solvability.p_value.toFixed(2)}`,
    result.solvability.p_value >= 0.5 ? 'good' : 'bad');
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginTop: 6 }}>
      {items.map((it, i) => (
        <span key={i} style={{
          fontSize: '0.7rem', fontWeight: 600, padding: '2px 8px', borderRadius: 999,
          background: t[it.tone].bg, color: t[it.tone].fg,
        }}>{it.label}</span>
      ))}
    </div>
  );
}

function QuestionRow({ q, onEvaluate, evaluating }) {
  const [showSource, setShowSource] = useState(false);
  return (
    <div style={{ borderTop: `1px solid var(--neutral-100)`, padding: '10px 0' }}>
      <div style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--neutral-800)', marginBottom: 4 }}>{q.question_text}</div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 4 }}>
        {(q.options || []).map((opt, i) => (
          <span key={i} style={{
            fontSize: '0.78rem', padding: '2px 8px', borderRadius: 6,
            background: i === q.correct_index ? '#ecfdf5' : 'var(--neutral-50)',
            color: i === q.correct_index ? '#166534' : 'var(--neutral-700)',
            border: `1px solid ${i === q.correct_index ? '#a7f3d0' : 'var(--neutral-200)'}`,
          }}>{i === q.correct_index ? '✓ ' : ''}{opt}</span>
        ))}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        {q.evaluated ? evalBadges(q.result) : (
          <button onClick={() => onEvaluate(q.eduqg_id)} disabled={evaluating} style={{
            fontSize: '0.78rem', padding: '4px 12px', borderRadius: 6, cursor: evaluating ? 'wait' : 'pointer',
            background: evaluating ? 'var(--neutral-200)' : TEAL, color: '#fff', border: 'none', marginTop: 4,
          }}>{evaluating ? 'Evaluiram...' : 'Evaluiraj ovo pitanje'}</button>
        )}
        {(q.grounding || q.context) && (
          <button onClick={() => setShowSource(!showSource)} style={{
            fontSize: '0.76rem', color: '#2563eb', background: 'none', border: 'none', cursor: 'pointer', padding: 0,
          }}>{showSource ? '▾ sakrij izvorni materijal' : '▸ izvorni materijal (na šta se proverava)'}</button>
        )}
      </div>
      {showSource && (
        <div style={{ marginTop: 8, background: 'var(--neutral-50)', border: '1px solid var(--neutral-200)', borderRadius: 8, padding: 10 }}>
          <div style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--neutral-600)', textTransform: 'uppercase', marginBottom: 3 }}>
            Ključne rečenice (grounding)
          </div>
          <div style={{ fontSize: '0.82rem', color: 'var(--neutral-700)', lineHeight: 1.5, marginBottom: 8 }}>
            {q.grounding || 'n/a'}
          </div>
          {q.context && (
            <>
              <div style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--neutral-600)', textTransform: 'uppercase', marginBottom: 3 }}>
                Širi pasus (koji CoVe koristi)
              </div>
              <div style={{ fontSize: '0.82rem', color: 'var(--neutral-700)', lineHeight: 1.5 }}>
                {q.context}
              </div>
            </>
          )}
          <div style={{ fontSize: '0.72rem', color: 'var(--neutral-500)', marginTop: 8, fontStyle: 'italic' }}>
            Izvor: EduQG skup (question-generation-main), polja hl_sentences i hl_context.
          </div>
        </div>
      )}
    </div>
  );
}

function BookSection({ book, onQuestionEvaluated }) {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState({ questions: [], total: 0, loading: false });
  const [evaluating, setEvaluating] = useState(null);

  const load = useCallback((offset) => {
    setState((s) => ({ ...s, loading: true }));
    eduqgApi.questions(book.book, offset, 20).then((res) => {
      setState((s) => ({
        questions: offset === 0 ? res.data.questions : [...s.questions, ...res.data.questions],
        total: res.data.total, loading: false,
      }));
    }).catch(() => setState((s) => ({ ...s, loading: false })));
  }, [book.book]);

  const toggle = () => {
    const next = !open; setOpen(next);
    if (next && state.questions.length === 0) load(0);
  };

  const handleEvaluate = (qid) => {
    setEvaluating(qid);
    eduqgApi.evaluate(qid).then((res) => {
      setState((s) => ({
        ...s,
        questions: s.questions.map((q) => q.eduqg_id === qid ? res.data.question : q),
      }));
      onQuestionEvaluated(res.data.expert);
    }).finally(() => setEvaluating(null));
  };

  return (
    <div style={{ border: `1px solid ${C.line}`, borderRadius: 10, marginBottom: 8, background: C.card }}>
      <button onClick={toggle} style={{
        width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '12px 16px', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left',
      }}>
        <span style={{ fontWeight: 600, color: 'var(--neutral-800)' }}>{open ? '▾' : '▸'} {bookLabel(book.book)}</span>
        <span style={{ fontSize: '0.8rem', color: C.muted }}>
          {book.evaluated} / {book.total} evaluirano
        </span>
      </button>
      {open && (
        <div style={{ padding: '0 16px 12px' }}>
          {state.questions.map((q) => (
            <QuestionRow key={q.eduqg_id} q={q} onEvaluate={handleEvaluate} evaluating={evaluating === q.eduqg_id} />
          ))}
          {state.loading && <div style={{ fontSize: '0.82rem', color: C.muted, padding: 8 }}>Učitavam...</div>}
          {!state.loading && state.questions.length < state.total && (
            <button onClick={() => load(state.questions.length)} style={{
              marginTop: 8, fontSize: '0.8rem', padding: '6px 14px', borderRadius: 6,
              background: 'var(--neutral-100)', border: `1px solid ${C.line}`, cursor: 'pointer',
            }}>Učitaj još ({state.total - state.questions.length})</button>
          )}
        </div>
      )}
    </div>
  );
}

// ---------- glavna komponenta ----------
function EduQGBenchmark() {
  const [state, setState] = useState({ loading: true });

  useEffect(() => {
    let cancelled = false;
    eduqgApi.overview()
      .then((res) => { if (!cancelled) setState({ loading: false, data: res.data }); })
      .catch((err) => { if (!cancelled) setState({ loading: false, error: err.message }); });
    return () => { cancelled = true; };
  }, []);

  // kada se novo pitanje evaluira, osveži ekspertske vrednosti i broj
  const onQuestionEvaluated = useCallback((expert) => {
    setState((s) => {
      if (!s.data) return s;
      const metrics = s.data.metrics.map((m) => m.comparable
        ? { ...m, expert: expert[m.key] } : m);
      return { ...s, data: { ...s.data, expert_n: expert.n, metrics } };
    });
  }, []);

  if (state.loading) return <div className="card"><p>Učitavam EduQG benchmark...</p></div>;
  if (state.error) return <div className="card"><p style={{ color: '#991b1b' }}>Greška: {state.error}</p></div>;
  const data = state.data;
  if (!data?.available) {
    return (
      <div className="card">
        <h2>EduQG Benchmark</h2>
        <p>{data?.reason || 'Podaci nisu dostupni.'}</p>
      </div>
    );
  }

  return (
    <div>
      <h2 style={{ marginBottom: 6 }}>EduQG Benchmark</h2>

      {/* objašnjenje */}
      <div style={{ background: '#f0f9f7', border: `1px solid #b8e0d8`, borderRadius: 12, padding: 16, marginBottom: 20 }}>
        <div style={{ fontWeight: 700, color: '#1d6f64', marginBottom: 6 }}>Šta je ovo i čemu služi?</div>
        <p style={{ fontSize: '0.9rem', color: 'var(--neutral-700)', margin: '0 0 8px', lineHeight: 1.55 }}>
          Naš sistem ima validatore koji ocenjuju kvalitet pitanja. Ovde proveravamo koliko su ti
          validatori dobro podešeni tako što ih puštamo na dve grupe pitanja i poredimo rezultate:
        </p>
        <ul style={{ fontSize: '0.9rem', color: 'var(--neutral-700)', margin: '0 0 8px', lineHeight: 1.55 }}>
          <li><strong>Naša pitanja</strong> (lekcije Procesi, Niti, Konkurentnost) koja je sistem sam generisao.</li>
          <li><strong>Ekspertska pitanja</strong> iz skupa EduQG, koja su pisali stručnjaci, pa ih smatramo dobrim.</li>
        </ul>
        <p style={{ fontSize: '0.9rem', color: 'var(--neutral-700)', margin: 0, lineHeight: 1.55 }}>
          Pošto su ekspertska pitanja dobra, ona su merilo kalibracije: ako validator često
          označi ekspertsko pitanje kao loše, on je prestrog. Trenutno je evaluirano <strong>{data.expert_n}</strong> od
          ukupno {data.dataset_total} ekspertskih pitanja. Možeš dodati još tako što ćeš ih
          evaluirati niže po oblastima, a statistika se odmah ažurira.
        </p>
      </div>

      {/* round-trip: generisanje iz istog izvornog materijala */}
      <div style={{ background: '#fbf7f0', border: `1px solid ${GOLD}55`, borderRadius: 12, padding: 16, marginBottom: 20 }}>
        <div style={{ fontWeight: 700, color: '#7a5b3a', marginBottom: 6 }}>
          Generiši svoja pitanja iz istog materijala
        </div>
        <p style={{ fontSize: '0.9rem', color: 'var(--neutral-700)', margin: '0 0 10px', lineHeight: 1.55 }}>
          Preuzmi izvorne pasuse (hl_context) iz kojih su izvedena ekspertska pitanja evaluiranog
          pilot skupa, spojene u jedan PDF i grupisane po udžbeniku i poglavlju. Otpremi taj PDF kao
          lekciju, parsiraj ga u sekcije i ishode učenja, pa generiši sopstvena pitanja — tako možeš
          direktno uporediti svoja pitanja sa EduQG ekspertskim za isti izvorni tekst.
        </p>
        <a
          href={eduqgApi.pilotSourcePdfUrl()}
          style={{
            display: 'inline-block', background: GOLD, color: '#fff', textDecoration: 'none',
            padding: '8px 16px', borderRadius: 8, fontSize: '0.88rem', fontWeight: 600,
          }}
        >
          Preuzmi izvorni materijal (PDF)
        </a>
      </div>

      {/* uporedive metrike */}
      <h3 style={{ fontSize: '1rem', color: 'var(--neutral-700)', margin: '0 0 6px' }}>
        Uporedive metrike: naša pitanja vs ekspertska
      </h3>
      <p style={{ fontSize: '0.86rem', color: C.muted, margin: '0 0 12px' }}>
        Ove mere postoje i za naša i za ekspertska pitanja, pa ih možemo direktno porediti.
        Tirkizne trake su naše tri lekcije, smeđa traka su ekspertska pitanja.
      </p>
      {data.metrics.filter((m) => m.comparable).map((m) => <MetricCard key={m.key} m={m} />)}

      {/* metrike samo za naša pitanja */}
      <h3 style={{ fontSize: '1rem', color: 'var(--neutral-700)', margin: '22px 0 6px' }}>
        Metrike samo za naša pitanja
      </h3>
      <p style={{ fontSize: '0.86rem', color: C.muted, margin: '0 0 12px' }}>
        Ekspertski skup EduQG nema dodeljene SOLO nivoe ni vezane ishode učenja, pa se za njegova
        pitanja ove mere ne mogu izračunati. Zato se ovde prikazuju samo vrednosti za naše tri
        lekcije, bez poređenja.
      </p>
      {data.metrics.filter((m) => !m.comparable).map((m) => <MetricCard key={m.key} m={m} />)}

      {/* pitanja po oblasti */}
      <h3 style={{ fontSize: '1rem', color: 'var(--neutral-700)', margin: '24px 0 10px' }}>
        Ekspertska pitanja po oblasti
      </h3>
      <p style={{ fontSize: '0.86rem', color: C.muted, margin: '0 0 12px' }}>
        Otvori oblast da vidiš pitanja. Za svako pitanje možeš pokrenuti evaluaciju; rezultat se
        prikazuje pored pitanja, a zbirna statistika gore se ažurira.
      </p>
      {data.books.map((b) => (
        <BookSection key={b.book} book={b} onQuestionEvaluated={onQuestionEvaluated} />
      ))}
    </div>
  );
}

export default EduQGBenchmark;
