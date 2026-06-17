from flask import Flask, render_template_string, jsonify
import csv
import json
import os
from datetime import datetime
import time # Non utilisé, mais laissé pour la conformité

# --- CONFIGURATION ---
LIVE_STATE_FILE = "dashboard_live_state.json" # Fichier JSON de l'état du compte en temps réel
TRADES_FILE = "trades_history_v2.csv"         # Fichier CSV de l'historique des trades
app = Flask(__name__)

# --- TEMPLATE HTML/CSS/JS V7 ---
# Le template contient la structure HTML, le style Tailwind CSS et toute la logique JavaScript (fetch/render/charts)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MonsterMind V7 | Analytics</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <style>
        :root { --sidebar-width: 260px; --bg-dark: #0f172a; --bg-card: #1e293b; --accent: #3b82f6; }
        body { background-color: var(--bg-dark); color: #cbd5e1; font-family: 'Inter', sans-serif; display: flex; height: 100vh; overflow: hidden; }
        
        aside { width: var(--sidebar-width); background-color: #111827; border-right: 1px solid #374151; display: flex; flex-direction: column; flex-shrink: 0; }
        .nav-link { display: flex; items-center; gap: 12px; padding: 12px 24px; color: #9ca3af; cursor: pointer; border-left: 3px solid transparent; transition: all 0.2s; }
        .nav-link:hover, .nav-link.active { background-color: #1f2937; color: white; border-left-color: var(--accent); }
        
        main { flex: 1; overflow-y: auto; padding: 32px; }
        
        .card { background-color: var(--bg-card); border-radius: 12px; padding: 24px; border: 1px solid #334155; box-shadow: 0 4px 6px rgba(0,0,0,0.2); }
        .stat-val { font-size: 1.8rem; font-weight: 700; color: white; }
        
        .text-win { color: #34d399; }
        .text-loss { color: #f87171; }
        .bg-win { background-color: rgba(52, 211, 153, 0.1); }
        .bg-loss { background-color: rgba(248, 113, 113, 0.1); }
        
        .page-section { display: none; animation: fadeIn 0.3s; }
        .page-section.active { display: block; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        
        table { width: 100%; border-collapse: collapse; }
        th { text-align: left; padding: 12px; color: #64748b; font-size: 0.75rem; text-transform: uppercase; border-bottom: 1px solid #334155; }
        td { padding: 14px 12px; border-bottom: 1px solid #334155; font-size: 0.9rem; }
    </style>
</head>
<body>

    <aside>
        <div class="p-6 border-b border-gray-800 flex items-center gap-3">
            <div class="h-10 w-10 rounded bg-blue-600 flex items-center justify-center text-white font-bold text-xl">M</div>
            <div>
                <h1 class="text-white font-bold">MonsterMind</h1>
                <p class="text-xs text-blue-400">V7 Analytics</p>
            </div>
        </div>
        
        <nav class="flex-1 py-6 space-y-1">
            <div class="nav-link active" onclick="switchPage('dashboard', this)"><i class="fas fa-home w-5"></i> Dashboard Live</div>
            <div class="nav-link" onclick="switchPage('positions', this)"><i class="fas fa-bolt w-5"></i> Positions <span id="pos-badge" class="ml-auto bg-blue-600 text-white text-xs px-2 rounded-full hidden">0</span></div>
            <div class="nav-link" onclick="switchPage('history', this)"><i class="fas fa-list w-5"></i> Historique</div>
            <div class="nav-link" onclick="switchPage('performance', this)"><i class="fas fa-chart-pie w-5"></i> Performance & Ratios</div>
        </nav>
        
        <div class="p-6 text-xs text-slate-500 border-t border-gray-800">
            Dernière MAJ: <span id="server-time" class="text-slate-300">--:--:--</span>
        </div>
    </aside>

    <main>
        
        <div id="dashboard" class="page-section active">
            <h2 class="text-2xl font-bold text-white mb-6">Vue d'ensemble</h2>
            
            <div class="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
                <div class="card border-l-4 border-blue-500">
                    <p class="text-sm text-slate-400 font-bold uppercase">Equity</p>
                    <p class="stat-val" id="kpi-equity">$0.00</p>
                </div>
                <div class="card border-l-4 border-purple-500">
                    <p class="text-sm text-slate-400 font-bold uppercase">Marge Libre</p>
                    <p class="stat-val" id="kpi-margin">$0.00</p>
                </div>
                <div class="card border-l-4 border-green-500">
                    <p class="text-sm text-slate-400 font-bold uppercase">Profit Flottant</p>
                    <p class="stat-val" id="kpi-pl">$0.00</p>
                </div>
                <div class="card border-l-4 border-orange-500">
                    <p class="text-sm text-slate-400 font-bold uppercase">Positions</p>
                    <p class="stat-val" id="kpi-count">0</p>
                </div>
            </div>
            
            <div class="card h-96">
                <h3 class="text-white font-bold mb-4">Activité Live (Equity)</h3>
                <canvas id="liveChart"></canvas>
            </div>
        </div>

        <div id="positions" class="page-section">
            <h2 class="text-2xl font-bold text-white mb-6">Positions Actives</h2>
            <div class="card p-0 overflow-hidden">
                <table class="w-full">
                    <thead class="bg-gray-800">
                        <tr>
                            <th>Ticket</th><th>Symbole</th><th>Type</th><th>Vol</th><th>Prix Ouv.</th><th>Prix Act.</th><th class="text-right">Profit</th>
                        </tr>
                    </thead>
                    <tbody id="positions-body"></tbody>
                </table>
            </div>
        </div>

        <div id="history" class="page-section">
            <div class="flex justify-between items-center mb-6">
                <h2 class="text-2xl font-bold text-white">Historique Complet</h2>
                <button onclick="fetchHistory()" class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded text-sm"><i class="fas fa-sync-alt mr-2"></i>Actualiser</button>
            </div>
            <div class="card p-0 overflow-hidden">
                <div class="overflow-y-auto max-h-[600px]">
                    <table class="w-full">
                        <thead class="bg-gray-800 sticky top-0">
                            <tr>
                                <th>Date</th><th>Symbole</th><th>Type</th><th>Score V4</th><th class="text-right">Profit</th>
                            </tr>
                        </thead>
                        <tbody id="history-body"></tbody>
                    </table>
                </div>
            </div>
        </div>

        <div id="performance" class="page-section">
            <h2 class="text-2xl font-bold text-white mb-6">Analyse de la Performance </h2>
            
            <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
                <div class="card flex items-center justify-between">
                    <div>
                        <p class="text-slate-400 text-xs uppercase font-bold">Total Gains ($)</p>
                        <p class="text-2xl font-bold text-win" id="perf-total-win">$0.00</p>
                    </div>
                    <i class="fas fa-arrow-trend-up text-win text-3xl opacity-50"></i>
                </div>
                <div class="card flex items-center justify-between">
                    <div>
                        <p class="text-slate-400 text-xs uppercase font-bold">Total Pertes ($)</p>
                        <p class="text-2xl font-bold text-loss" id="perf-total-loss">$0.00</p>
                    </div>
                    <i class="fas fa-arrow-trend-down text-loss text-3xl opacity-50"></i>
                </div>
                <div class="card flex items-center justify-between">
                    <div>
                        <p class="text-slate-400 text-xs uppercase font-bold">Net Profit</p>
                        <p class="text-2xl font-bold text-white" id="perf-net">$0.00</p>
                    </div>
                    <i class="fas fa-wallet text-blue-500 text-3xl opacity-50"></i>
                </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
                <div class="card flex items-center justify-between border-l-4 border-slate-500">
                    <div>
                        <p class="text-slate-400 text-xs uppercase font-bold">Total Trades Clôturés</p>
                        <p class="text-2xl font-bold text-white" id="perf-total-count">0</p>
                    </div>
                    <i class="fas fa-chart-line text-slate-500 text-3xl opacity-50"></i>
                </div>
                <div class="card flex items-center justify-between border-l-4 border-green-500">
                    <div>
                        <p class="text-slate-400 text-xs uppercase font-bold">Trades Gagnants</p>
                        <p class="text-2xl font-bold text-win" id="perf-win-count">0</p>
                    </div>
                    <i class="fas fa-check-circle text-win text-3xl opacity-50"></i>
                </div>
                <div class="card flex items-center justify-between border-l-4 border-red-500">
                    <div>
                        <p class="text-slate-400 text-xs uppercase font-bold">Trades Perdants</p>
                        <p class="text-2xl font-bold text-loss" id="perf-loss-count">0</p>
                    </div>
                    <i class="fas fa-times-circle text-loss text-3xl opacity-50"></i>
                </div>
            </div>
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div class="card">
                    <h3 class="text-white font-bold mb-4 border-b border-gray-700 pb-2">Ratio Win Rate (Nombre de trades)</h3>
                    <div class="h-64 flex justify-center relative">
                        <canvas id="winRateChart"></canvas>
                        <div class="absolute inset-0 flex items-center justify-center pointer-events-none">
                            <span class="text-2xl font-bold text-white" id="win-rate-text">0%</span>
                        </div>
                    </div>
                </div>

                <div class="card">
                    <h3 class="text-white font-bold mb-4 border-b border-gray-700 pb-2">Répartition Gains vs Pertes ($)</h3>
                    <div class="h-64">
                        <canvas id="plRatioChart"></canvas>
                    </div>
                </div>
            </div>
        </div>

    </main>

    <script>
        // --- LOGIQUE JS ---
        let winRateChart = null;
        let plRatioChart = null;
        let liveChart = null;
        const liveEquityData = [];

        function switchPage(id, el) {
            document.querySelectorAll('.page-section').forEach(d => d.classList.remove('active'));
            document.getElementById(id).classList.add('active');
            document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
            el.classList.add('active');
            
            if(id === 'performance' || id === 'history') fetchHistory();
        }

        // 1. MISE À JOUR LIVE (Rapide)
        async function updateLive() {
            try {
                const res = await fetch('/api/live');
                const data = await res.json();
                
                if(data.status === 'offline') return;

                document.getElementById('server-time').innerText = new Date(data.last_update).toLocaleTimeString();
                
                // KPIs
                const acc = data.account;
                document.getElementById('kpi-equity').innerText = '$' + acc.equity.toFixed(2);
                document.getElementById('kpi-margin').innerText = '$' + acc.margin.toFixed(2);
                document.getElementById('kpi-count').innerText = data.open_positions.length;
                
                // Badge
                const badge = document.getElementById('pos-badge');
                if (data.open_positions.length > 0) {
                    badge.innerText = data.open_positions.length;
                    badge.classList.remove('hidden');
                } else {
                    badge.classList.add('hidden');
                }

                // Profit Flottant
                let floating = 0;
                let htmlPos = '';
                data.open_positions.forEach(p => {
                    floating += p.profit;
                    const color = p.profit >= 0 ? 'text-win' : 'text-loss';
                    htmlPos += `
                        <tr class="hover:bg-slate-800 transition">
                            <td>${p.ticket}</td>
                            <td class="font-bold text-white">${p.symbol}</td>
                            <td><span class="text-xs font-bold px-2 py-1 rounded ${p.type=='BUY'?'bg-win':'bg-loss'}">${p.type}</span></td>
                            <td>${p.volume}</td>
                            <td class="text-slate-400">${p.price_open}</td>
                            <td class="text-white">${p.price_current}</td>
                            <td class="font-bold text-right ${color}">${p.profit.toFixed(2)} $</td>
                        </tr>
                    `;
                });
                
                const plEl = document.getElementById('kpi-pl');
                plEl.innerText = (floating>=0?'+':'') + '$' + floating.toFixed(2);
                plEl.className = 'stat-val ' + (floating>=0?'text-win':'text-loss');
                
                // Tableau Positions
                const tbody = document.getElementById('positions-body');
                tbody.innerHTML = htmlPos || '<tr><td colspan="7" class="text-center py-8 text-slate-500">Aucune position</td></tr>';

                // Graphique Live
                if(liveEquityData.length > 50) liveEquityData.shift();
                liveEquityData.push(acc.equity);
                renderLiveChart(liveEquityData);

            } catch(e) { console.error(e); }
        }

        // 2. RÉCUPÉRATION HISTORIQUE (Lourd)
        async function fetchHistory() {
            try {
                const res = await fetch('/api/history');
                const data = await res.json();
                
                renderHistoryTable(data.trades);
                renderPerformanceCharts(data);
                
            } catch(e) { console.error(e); }
        }

        function renderHistoryTable(trades) {
            const tbody = document.getElementById('history-body');
            if(!trades || trades.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" class="text-center py-8 text-slate-500">Aucune donnée historique</td></tr>';
                return;
            }
            
            let html = '';
            // Afficher du plus récent au plus ancien
            [...trades].reverse().forEach(t => {
                const color = t.profit >= 0 ? 'text-win' : 'text-loss';
                const date = new Date(t.time).toLocaleString();
                html += `
                    <tr class="hover:bg-slate-800 transition border-b border-gray-800">
                        <td class="text-xs text-slate-400 font-mono">${date}</td>
                        <td class="font-bold text-white">${t.symbol}</td>
                        <td><span class="text-xs font-bold px-2 py-0.5 rounded ${t.type=='BUY'?'bg-win':'bg-loss'}">${t.type}</span></td>
                        <td class="text-xs font-mono text-blue-400">${t.score.toFixed(2)}</td>
                        <td class="font-bold text-right ${color}">${t.profit.toFixed(2)} $</td>
                    </tr>
                `;
            });
            tbody.innerHTML = html;
        }

        function renderPerformanceCharts(data) {
            // KPIs Performance (Gains/Pertes)
            document.getElementById('perf-total-win').innerText = '+ $' + data.stats.gross_profit.toFixed(2);
            document.getElementById('perf-total-loss').innerText = '- $' + Math.abs(data.stats.gross_loss).toFixed(2);
            const net = data.stats.net_profit;
            const netEl = document.getElementById('perf-net');
            netEl.innerText = (net>=0?'+':'') + '$' + net.toFixed(2);
            netEl.className = 'text-2xl font-bold ' + (net>=0?'text-win':'text-loss');
            
            // NOUVEAU: KPIs Compteurs de trades
            document.getElementById('perf-total-count').innerText = data.stats.count;
            document.getElementById('perf-win-count').innerText = data.stats.win_count;
            document.getElementById('perf-loss-count').innerText = data.stats.loss_count;
            // FIN NOUVEAU

            document.getElementById('win-rate-text').innerText = data.stats.win_rate.toFixed(1) + '%';

            // Chart 1: Win/Loss Ratio (Doughnut) 
            const ctx1 = document.getElementById('winRateChart').getContext('2d');
            if(winRateChart) winRateChart.destroy();
            
            winRateChart = new Chart(ctx1, {
                type: 'doughnut',
                data: {
                    labels: ['Gagnants', 'Perdants'],
                    datasets: [{
                        data: [data.stats.win_count, data.stats.loss_count],
                        backgroundColor: ['#10b981', '#ef4444'],
                        borderWidth: 0,
                        hoverOffset: 4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: '75%',
                    plugins: { legend: { position: 'bottom', labels: { color: '#cbd5e1' } } }
                }
            });

            // Chart 2: P/L Volume (Bar) 
            const ctx2 = document.getElementById('plRatioChart').getContext('2d');
            if(plRatioChart) plRatioChart.destroy();
            
            plRatioChart = new Chart(ctx2, {
                type: 'bar',
                data: {
                    labels: ['Volume Gains', 'Volume Pertes'],
                    datasets: [{
                        label: 'Montant ($)',
                        data: [data.stats.gross_profit, Math.abs(data.stats.gross_loss)],
                        backgroundColor: ['#10b981', '#ef4444'],
                        borderRadius: 6
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    indexAxis: 'y',
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { grid: { color: '#334155' }, ticks: { color: '#94a3b8' } },
                        y: { grid: { display: false }, ticks: { color: 'white', font: {weight:'bold'} } }
                    }
                }
            });
        }
        
        function renderLiveChart(data) {
            const ctx = document.getElementById('liveChart').getContext('2d');
            if (!liveChart) {
                liveChart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: Array(50).fill(''),
                        datasets: [{
                            data: data,
                            borderColor: '#3b82f6',
                            backgroundColor: 'rgba(59, 130, 246, 0.1)',
                            borderWidth: 2,
                            fill: true,
                            pointRadius: 0,
                            tension: 0.4
                        }]
                    },
                    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { display: false }, y: { grid: { color: '#1e293b' }, ticks: { color: '#64748b' } } }, animation: false }
                });
            } else {
                liveChart.data.datasets[0].data = data;
                liveChart.update();
            }
        }

        // Boucles de rafraîchissement
        setInterval(updateLive, 1000);
        fetchHistory();
        setInterval(fetchHistory, 10000);
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    """Route principale, rend le template HTML du tableau de bord."""
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/live')
def api_live():
    """API pour l'état en temps réel (lu depuis le fichier JSON)."""
    if os.path.exists(LIVE_STATE_FILE):
        try:
            # 1. Lecture complète du fichier en mémoire
            with open(LIVE_STATE_FILE, 'r') as f:
                raw_data = f.read()
            
            # 2. Parsing JSON sécurisé
            if raw_data:
                data = json.loads(raw_data)
                return jsonify(data)
                
        except json.JSONDecodeError:
            # Erreur si le fichier était en cours d'écriture (JSON incomplet)
            print(f"⚠️ Erreur de décodage JSON dans {LIVE_STATE_FILE}. Tente à nouveau.")
            pass
        except Exception as e:
            # Autres erreurs (I/O)
            print(f"❌ Erreur inattendue lors de la lecture de {LIVE_STATE_FILE}: {e}")
            pass
            
    # Retourne l'état hors ligne si le fichier n'existe pas ou si la lecture/parsing a échoué
    return jsonify({
        "status": "offline", 
        "last_update": datetime.now().isoformat(),
        "account": {"equity":0.0, "margin":0.0}, 
        "open_positions":[]
    })

@app.route('/api/history')
def api_history():
    """API pour l'historique et les statistiques (lu depuis le fichier CSV)."""
    trades = []
    if os.path.exists(TRADES_FILE):
        try:
            with open(TRADES_FILE, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        # Assurer que les valeurs numériques sont correctement typées (gérer None ou chaîne vide)
                        score_val = row.get('score')
                        profit_val = row.get('profit')
                        
                        trades.append({
                            "time": row.get('timestamp') or row.get('time'),
                            "symbol": row.get('symbol'),
                            "type": row.get('direction'),
                            # Utiliser 0.0 si la valeur est manquante ou vide
                            "score": float(score_val) if score_val and score_val.strip() else 0.0,
                            "profit": float(profit_val) if profit_val and profit_val.strip() else 0.0
                        })
                    except ValueError:
                        # Se produit si 'score' ou 'profit' ne peuvent pas être convertis en float
                        print(f"❌ Valeur non numérique dans l'historique : {row}")
                        continue
                    except: 
                        continue
        except Exception as e:
            print(f"❌ Erreur de lecture du fichier CSV d'historique : {e}")
            pass
        
    # Calcul des stats avancées pour l'onglet Performance
    wins = [t for t in trades if t['profit'] > 0]
    losses = [t for t in trades if t['profit'] < 0]
    
    total_trades = len(trades)
    
    stats = {
        "count": total_trades,
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate": (len(wins)/total_trades*100) if total_trades > 0 else 0.0,
        "gross_profit": sum(t['profit'] for t in wins),
        "gross_loss": sum(t['profit'] for t in losses),
        "net_profit": sum(t['profit'] for t in trades)
    }
    
    return jsonify({"trades": trades, "stats": stats})

if __name__ == '__main__':
    print("🚀 Dashboard V7 PRO démarré : http://127.0.0.1:5000")
    # Conserver use_reloader=False pour éviter des interférences avec les fichiers live
    app.run(debug=True, port=5000, use_reloader=False)