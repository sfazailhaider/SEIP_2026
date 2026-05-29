import gzip
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from plotly.subplots import make_subplots
from collections import defaultdict
from datetime import datetime
from scipy import stats

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title='Watch Reviews Dashboard',
    page_icon='⌚',
    layout='wide',
    initial_sidebar_state='expanded',
)

st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; padding-bottom: 1rem; }
    .kpi-card {
        background: #13151f;
        border-radius: 10px;
        padding: 1.1rem 1rem 0.8rem;
        text-align: center;
        border: 1px solid;
    }
    .kpi-value { font-size: 1.9rem; font-weight: 700; margin: 0; }
    .kpi-label { font-size: 0.8rem; font-weight: 600; color: #c0c4d6; margin: 4px 0 2px; }
    .kpi-sub   { font-size: 0.72rem; color: #6b7280; margin: 0; }
    [data-testid="stSidebar"] { background: #0f1117; }
</style>
""", unsafe_allow_html=True)

# ── Colours ───────────────────────────────────────────────────────────────────

BG    = '#0b0d14'
CARD  = '#13151f'
BORD  = '#1e2130'
BLUE  = '#4f8ef7'
GREEN = '#3ecf8e'
AMBER = '#f5a623'
RED   = '#f25b5b'
PURP  = '#a78bfa'
TXT   = '#e2e4ef'
MUT   = '#6b7280'

PLOTLY_LAYOUT = dict(
    paper_bgcolor=BG,
    plot_bgcolor=CARD,
    font_color=TXT,
    font_size=11,
    margin=dict(l=10, r=10, t=36, b=10),
    xaxis=dict(gridcolor=BORD, linecolor=BORD, tickfont_color=MUT, title_font_color=MUT),
    yaxis=dict(gridcolor=BORD, linecolor=BORD, tickfont_color=MUT, title_font_color=MUT),
)

def apply_layout(fig, title='', **kwargs):
    fig.update_layout(**PLOTLY_LAYOUT, title=dict(text=title, font_size=13, x=0), **kwargs)
    return fig

# ── Parse / load ──────────────────────────────────────────────────────────────

def parse(fileobj):
    with gzip.open(fileobj, 'rt', encoding='latin-1') as f:
        entry = {}
        for line in f:
            line = line.strip()
            colon = line.find(':')
            if colon == -1:
                if entry:
                    yield entry
                entry = {}
                continue
            entry[line[:colon]] = line[colon + 2:]
        if entry:
            yield entry

def load(fileobj):
    records = []
    for e in parse(fileobj):
        try:
            records.append({
                'product_id':  e.get('product/productId', ''),
                'title':       e.get('product/title', 'Unknown'),
                'price':       e.get('product/price', 'unknown'),
                'user_id':     e.get('review/userId', ''),
                'helpfulness': e.get('review/helpfulness', '0/0'),
                'score':       float(e.get('review/score', 0)),
                'time':        int(e.get('review/time', 0)),
                'text':        e.get('review/text', ''),
            })
        except (ValueError, KeyError):
            continue
    return records

@st.cache_data(show_spinner='Loading reviews…')
def load_and_enrich(file_bytes, filename):
    import io
    records = load(io.BytesIO(file_bytes))
    for r in records:
        num, den = r['helpfulness'].split('/')
        r['helpful_votes'] = int(num)
        r['total_votes']   = int(den)
        r['helpful_ratio'] = int(num) / int(den) if int(den) > 0 else None
        r['date']          = datetime.fromtimestamp(r['time']) if r['time'] else None
        r['review_length'] = len(r['text'].split())
        try:
            r['price_val'] = float(r['price'].replace('$', '').replace(',', ''))
        except ValueError:
            r['price_val'] = None
    return records

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown('## ⌚ Watch Reviews')
    st.markdown('---')
    uploaded = st.file_uploader('Upload your `.txt.gz` file', type=['gz'])
    st.markdown('---')
    st.markdown('**Filters**')

if uploaded is None:
    st.markdown(
        '<div style="text-align:center;padding:4rem 2rem;color:#6b7280;">'
        '<p style="font-size:2rem">⌚</p>'
        '<p style="font-size:1.1rem;font-weight:600;color:#c0c4d6;">Upload a review file to get started</p>'
        '<p style="font-size:0.85rem">Use the sidebar to upload your <code>.txt.gz</code> file</p>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.stop()

records = load_and_enrich(uploaded.read(), uploaded.name)

# ── Sidebar filters ───────────────────────────────────────────────────────────

scores_all = sorted(set(r['score'] for r in records))
dated      = [r for r in records if r['date']]
yr_min     = min(r['date'].year for r in dated) if dated else 2000
yr_max     = max(r['date'].year for r in dated) if dated else 2024

with st.sidebar:
    year_range = st.slider('Year range', yr_min, yr_max, (yr_min, yr_max))
    star_filter = st.multiselect(
        'Star ratings', options=[1, 2, 3, 4, 5],
        default=[1, 2, 3, 4, 5],
        format_func=lambda x: f'{"★" * x}',
    )

records = [
    r for r in records
    if r['score'] in star_filter
    and (r['date'] is None or year_range[0] <= r['date'].year <= year_range[1])
]

if not records:
    st.warning('No reviews match the current filters.')
    st.stop()

# ── Aggregate ─────────────────────────────────────────────────────────────────

n      = len(records)
scores = [r['score'] for r in records]
dated  = [r for r in records if r['date']]

avg_rating   = np.mean(scores)
pct_5        = scores.count(5.0) / n * 100
help_vals    = [r['helpful_ratio'] for r in records if r['helpful_ratio'] is not None]
avg_help     = np.mean(help_vals) * 100 if help_vals else 0
avg_len      = np.mean([r['review_length'] for r in records])
unique_prods = len(set(r['product_id'] for r in records))
unique_users = len(set(r['user_id'] for r in records))

m_vol   = defaultdict(int)
m_score = defaultdict(list)
for r in dated:
    key = r['date'].strftime('%Y-%m')
    m_vol[key]   += 1
    m_score[key].append(r['score'])
months     = sorted(m_vol)
vol_series = [m_vol[m] for m in months]
avg_series = [np.mean(m_score[m]) for m in months]

help_star = defaultdict(list)
len_star  = defaultdict(list)
for r in records:
    len_star[r['score']].append(r['review_length'])
    if r['helpful_ratio'] is not None:
        help_star[r['score']].append(r['helpful_ratio'])

prod_n = defaultdict(int)
prod_s = defaultdict(list)
for r in records:
    t = r['title'][:32]
    prod_n[t] += 1
    prod_s[t].append(r['score'])
top10      = sorted(prod_n, key=lambda x: -prod_n[x])[:10]
top_counts = [prod_n[p] for p in top10]
top_avg    = [np.mean(prod_s[p]) for p in top10]

pp = defaultdict(lambda: {'px': [], 'py': []})
for r in records:
    if r['price_val']:
        pp[r['product_id']]['px'].append(r['price_val'])
        pp[r['product_id']]['py'].append(r['score'])
scatter_px = [np.mean(v['px']) for v in pp.values()]
scatter_py = [np.mean(v['py']) for v in pp.values()]

sentiment = [
    sum(1 for r in records if r['score'] <= 2),
    sum(1 for r in records if r['score'] == 3),
    sum(1 for r in records if r['score'] >= 4),
]

user_counts = defaultdict(int)
for r in records:
    user_counts[r['user_id']] += 1
uc = list(user_counts.values())

# ── Header ────────────────────────────────────────────────────────────────────

st.markdown(f'## Watch Reviews — KPI Dashboard')
st.markdown(
    f'<p style="color:{MUT};font-size:0.85rem;margin-top:-0.5rem">'
    f'{n:,} reviews · {unique_prods:,} products · '
    f'{(min(r["date"].year for r in dated) if dated else "?")}–'
    f'{(max(r["date"].year for r in dated) if dated else "?")}'
    f'</p>', unsafe_allow_html=True
)

# ── KPI tiles ─────────────────────────────────────────────────────────────────

k1, k2, k3, k4, k5, k6 = st.columns(6)
kpi_data = [
    (k1, f'{avg_rating:.2f} ★', 'Avg rating',        'out of 5.0',                  BLUE),
    (k2, f'{pct_5:.1f}%',       '5-star share',       'of filtered reviews',         GREEN),
    (k3, f'{avg_help:.0f}%',    'Helpfulness rate',   'avg across voters',           AMBER),
    (k4, f'{avg_len:.0f}w',     'Avg review length',  '',                            PURP),
    (k5, f'{unique_prods:,}',   'Unique products',    '',                            BLUE),
    (k6, f'{unique_users:,}',   'Unique reviewers',   '',                            GREEN),
]
for col, val, label, sub, color in kpi_data:
    with col:
        st.markdown(
            f'<div class="kpi-card" style="border-color:{color}20;">'
            f'<p class="kpi-value" style="color:{color}">{val}</p>'
            f'<p class="kpi-label">{label}</p>'
            f'<p class="kpi-sub">{sub}</p>'
            f'</div>',
            unsafe_allow_html=True,
        )

st.markdown('<div style="margin-top:1.2rem"></div>', unsafe_allow_html=True)

# ── Row 1: volume + avg score ─────────────────────────────────────────────────

c1, c2 = st.columns(2)

with c1:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=months, y=vol_series, mode='lines',
        line=dict(color=BLUE, width=2),
        fill='tozeroy', fillcolor='rgba(79,142,247,0.1)',
        name='Reviews / month',
    ))
    apply_layout(fig, 'Review volume over time')
    fig.update_xaxes(tickangle=-35)
    st.plotly_chart(fig, use_container_width=True)

with c2:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=months, y=avg_series, mode='lines',
        line=dict(color=PURP, width=2),
        fill='tozeroy', fillcolor='rgba(167,139,250,0.08)',
        name='Avg rating',
    ))
    fig.add_hline(y=avg_rating, line_dash='dash', line_color=MUT,
                  annotation_text=f'Mean {avg_rating:.2f}',
                  annotation_font_color=MUT)
    apply_layout(fig, 'Average rating over time')
    fig.update_xaxes(tickangle=-35)
    fig.update_yaxes(range=[1, 5.2])
    st.plotly_chart(fig, use_container_width=True)

# ── Row 2: score dist + donut + helpfulness + length ─────────────────────────

c1, c2, c3, c4 = st.columns(4)

with c1:
    sc_counts = [scores.count(float(s)) for s in [1, 2, 3, 4, 5]]
    bar_cols  = [RED, AMBER, AMBER, GREEN, GREEN]
    fig = go.Figure(go.Bar(
        x=['1★', '2★', '3★', '4★', '5★'], y=sc_counts,
        marker_color=bar_cols,
        text=[f'{c/n*100:.1f}%' for c in sc_counts],
        textposition='outside', textfont_color=TXT,
    ))
    apply_layout(fig, 'Score distribution')
    st.plotly_chart(fig, use_container_width=True)

with c2:
    fig = go.Figure(go.Pie(
        labels=['Negative (1–2★)', 'Neutral (3★)', 'Positive (4–5★)'],
        values=sentiment,
        marker_colors=[RED, AMBER, GREEN],
        hole=0.55,
        textinfo='percent',
        textfont_color=TXT,
    ))
    fig.add_annotation(
        text=f'{sentiment[2]/n*100:.0f}%<br>positive',
        x=0.5, y=0.5, showarrow=False,
        font=dict(size=13, color=TXT),
    )
    apply_layout(fig, 'Sentiment split', showlegend=True,
                 legend=dict(font_color=TXT, bgcolor=CARD, bordercolor=BORD))
    st.plotly_chart(fig, use_container_width=True)

with c3:
    hx = sorted(help_star)
    hy = [np.mean(help_star[s]) * 100 for s in hx]
    hc = [RED if s <= 2 else (AMBER if s == 3 else GREEN) for s in hx]
    fig = go.Figure(go.Bar(
        x=[f'{int(s)}★' for s in hx], y=hy,
        marker_color=hc,
        text=[f'{v:.0f}%' for v in hy],
        textposition='outside', textfont_color=TXT,
    ))
    apply_layout(fig, 'Helpfulness by star')
    fig.update_yaxes(range=[0, 115])
    st.plotly_chart(fig, use_container_width=True)

with c4:
    lx = sorted(len_star)
    ly = [np.mean(len_star[s]) for s in lx]
    lc = [RED, AMBER, AMBER, GREEN, GREEN]
    fig = go.Figure(go.Bar(
        x=[f'{int(s)}★' for s in lx], y=ly,
        marker_color=lc,
        text=[f'{v:.0f}w' for v in ly],
        textposition='outside', textfont_color=TXT,
    ))
    apply_layout(fig, 'Review length by star')
    st.plotly_chart(fig, use_container_width=True)

# ── Row 3: top 10 products ────────────────────────────────────────────────────

colors_top = [GREEN if s >= 4 else (AMBER if s >= 3 else RED) for s in top_avg]
fig = go.Figure(go.Bar(
    x=top_counts,
    y=top10,
    orientation='h',
    marker_color=colors_top,
    text=[f'{a:.2f}★  ({c:,})' for a, c in zip(top_avg, top_counts)],
    textposition='outside',
    textfont_color=MUT,
))
apply_layout(fig, 'Top 10 products by review count', height=340)
fig.update_layout(yaxis=dict(autorange='reversed', gridcolor=BORD,
                              linecolor=BORD, tickfont_color=TXT, title_font_color=MUT))
st.plotly_chart(fig, use_container_width=True)

# ── Row 4: price vs score + reviewer activity ─────────────────────────────────

c1, c2 = st.columns(2)

with c1:
    fig = go.Figure()
    if len(scatter_px) > 10:
        fig.add_trace(go.Scatter(
            x=scatter_px, y=scatter_py,
            mode='markers',
            marker=dict(color=BLUE, size=5, opacity=0.4),
            name='Product',
        ))
        sl, ic, r_val, _, _ = stats.linregress(scatter_px, scatter_py)
        xl = np.linspace(min(scatter_px), max(scatter_px), 200)
        fig.add_trace(go.Scatter(
            x=xl, y=sl * xl + ic,
            mode='lines', line=dict(color=AMBER, width=2),
            name=f'Trend (r={r_val:.2f})',
        ))
    else:
        fig.add_annotation(text='Not enough priced products',
                           x=0.5, y=0.5, showarrow=False, font_color=MUT)
    apply_layout(fig, 'Price vs average rating',
                 showlegend=True,
                 legend=dict(font_color=TXT, bgcolor=CARD, bordercolor=BORD))
    fig.update_yaxes(range=[0.8, 5.2])
    fig.update_xaxes(title_text='Price ($)', title_font_color=MUT)
    fig.update_yaxes(title_text='Avg ★', title_font_color=MUT)
    st.plotly_chart(fig, use_container_width=True)

with c2:
    bins   = [1, 2, 3, 5, 10, 20, 50, 100, max(uc) + 1]
    hist, _ = np.histogram(uc, bins=bins)
    xlabels = ['1', '2', '3', '4–5', '6–10', '11–20', '21–50', '50+']
    fig = go.Figure(go.Bar(
        x=xlabels, y=hist,
        marker_color=PURP,
        text=[f'{v:,}' for v in hist],
        textposition='outside', textfont_color=TXT,
    ))
    apply_layout(fig, 'Reviewer activity')
    fig.update_xaxes(title_text='Reviews written', title_font_color=MUT)
    fig.update_yaxes(title_text='Users', title_font_color=MUT)
    st.plotly_chart(fig, use_container_width=True)
