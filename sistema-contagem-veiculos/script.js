const API_BASE = "http://localhost:8000";
const WS_URL   = "ws://localhost:8000/ws";
const UPDATE_INTERVAL = 5000;

let resumoChart, evolucaoChart, heatmapChart;
let socket;

// =========================
// Helpers
// =========================

function ultimos7Dias() {
    const agora = new Date();
    const inicio = new Date(agora.getTime() - 7*24*60*60*1000);
    return {
        inicio: inicio.toISOString().slice(0,16),
        fim: agora.toISOString().slice(0,16)
    };
}

// =========================
// Charts
// =========================

function initCharts() {

    resumoChart = new Chart(document.getElementById("resumoChart"), {
        type: "bar",
        data: { labels: [], datasets: [{ label: "Total", data: [] }] }
    });

    evolucaoChart = new Chart(document.getElementById("evolucaoChart"), {
        type: "line",
        data: { labels: [], datasets: [{ label: "Total", data: [] }] }
    });

    heatmapChart = new Chart(document.getElementById("heatmapChart"), {
        type: "bar",
        data: { labels: [], datasets: [{ label: "Total por Dia", data: [] }] }
    });
}

// =========================
// API Calls
// =========================

async function carregarResumo() {

    const {inicio, fim} = ultimos7Dias();

    const res = await fetch(
        `${API_BASE}/api/historico/agregado?inicio=${inicio}&fim=${fim}&granularidade=dia`
    );

    const data = await res.json();

    const labels = data.map(d => d.periodo);
    const totais = data.map(d => d.total);

    resumoChart.data.labels = labels;
    resumoChart.data.datasets[0].data = totais;
    resumoChart.update();
}

async function carregarEvolucao() {

    const {inicio, fim} = ultimos7Dias();
    const modo = document.getElementById("evolucaoSelect").value;

    const res = await fetch(
        `${API_BASE}/api/historico/agregado?inicio=${inicio}&fim=${fim}&granularidade=${modo}`
    );

    const data = await res.json();

    evolucaoChart.data.labels = data.map(d => d.periodo);
    evolucaoChart.data.datasets[0].data = data.map(d => d.total);
    evolucaoChart.update();
}

async function carregarHeatmap() {

    const {inicio, fim} = ultimos7Dias();

    const res = await fetch(
        `${API_BASE}/api/historico/filtrado?inicio=${inicio}&fim=${fim}&limite=10000`
    );

    const data = await res.json();

    const mapa = {};

    data.forEach(e => {
        const dt = new Date(e.timestamp);
        const dia = dt.toLocaleDateString();
        const hora = dt.getHours();

        if(!mapa[dia]) mapa[dia] = {};
        mapa[dia][hora] = (mapa[dia][hora] || 0) + 1;
    });

    const labels = Object.keys(mapa);
    const totais = labels.map(d => 
        Object.values(mapa[d]).reduce((a,b)=>a+b,0)
    );

    heatmapChart.data.labels = labels;
    heatmapChart.data.datasets[0].data = totais;
    heatmapChart.update();
}

// =========================
// WebSocket
// =========================

function conectarWS() {

    socket = new WebSocket(WS_URL);

    socket.onopen = () => console.log("WS conectado");

    socket.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if(msg.tipo === "contadores") {
            carregarResumo();
            carregarEvolucao();
            carregarHeatmap();
        }
    };

    socket.onclose = () => {
        console.log("WS desconectado. Reconectando...");
        setTimeout(conectarWS, 3000);
    };
}

// =========================
// Export
// =========================

async function exportExcel() {

    const {inicio, fim} = ultimos7Dias();

    const res = await fetch(
        `${API_BASE}/api/historico/filtrado?inicio=${inicio}&fim=${fim}&limite=10000`
    );

    const data = await res.json();

    const ws = XLSX.utils.json_to_sheet(data);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Dados");
    XLSX.writeFile(wb, "dashboard.xlsx");
}

function exportPDF() {
    const doc = new jspdf.jsPDF();
    doc.text("Dashboard Monitoramento - Últimos 7 dias", 20, 20);
    doc.save("dashboard.pdf");
}

// =========================
// Init
// =========================

document.getElementById("evolucaoSelect")
    .addEventListener("change", carregarEvolucao);

initCharts();
carregarResumo();
carregarEvolucao();
carregarHeatmap();
conectarWS();