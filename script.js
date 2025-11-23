const API = {
    async request(url, method, data) {
        try {
            const options = { method: method, headers: { "Content-Type": "application/json" } };
            if (data) options.body = JSON.stringify(data);
            const response = await fetch(url, options);
            if (response.status === 401) { window.location.href = "/login"; return null; }
            return await response.json();
        } catch (error) { console.error(error); return { error: "Connection failed" }; }
    },
    get: (url) => API.request(url, "GET"),
    post: (url, data) => API.request(url, "POST", data),
    put: (url, data) => API.request(url, "PUT", data),
    del: (url) => API.request(url, "DELETE")
};

const fmt = (num) => "₹" + Number(num || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 });
let activeCharts = []; // Track charts to destroy them before page swap

/* --- THEME --- */
function initTheme() { if (localStorage.getItem('theme') === 'dark') document.body.classList.add('dark'); }
function toggleTheme() {
    document.body.classList.toggle('dark');
    localStorage.setItem('theme', document.body.classList.contains('dark') ? 'dark' : 'light');
}
initTheme();

/* --- SPA ROUTER (SMOOTH TRANSITIONS) --- */
document.addEventListener('DOMContentLoaded', () => {
    // Initial Load
    handleLocation();

    // Intercept clicks
    document.body.addEventListener('click', e => {
        const link = e.target.closest('a');
        // Only intercept internal links in the sidebar nav
        if (link && link.getAttribute('href').startsWith('/') && link.closest('.nav-links')) {
            e.preventDefault();
            navigateTo(link.getAttribute('href'));
        }
    });
});

async function navigateTo(url) {
    // Visual feedback on nav
    document.querySelectorAll('.nav-links a').forEach(a => a.classList.remove('active'));
    const activeLink = document.querySelector(`.nav-links a[href="${url}"]`);
    if (activeLink) activeLink.classList.add('active');

    // Animate Out
    const container = document.getElementById('app-content');
    if (container) {
        container.classList.add('page-exit');
        container.classList.remove('page-enter');
    }

    // Fetch & Swap
    try {
        const response = await fetch(url);
        const html = await response.text();
        const parser = new DOMParser();
        const doc = parser.parseFromString(html, 'text/html');
        
        // Wait a tiny bit for exit animation
        setTimeout(() => {
            const newContent = doc.getElementById('app-content').innerHTML;
            if (container) {
                container.innerHTML = newContent;
                container.classList.remove('page-exit');
                container.classList.add('page-enter');
                window.history.pushState(null, '', url);
                handleLocation(); // Re-init scripts for new page
            }
        }, 200); // Match slideOut duration
    } catch (err) {
        console.error('Nav error', err);
        window.location.href = url; // Fallback
    }
}

function handleLocation() {
    const path = window.location.pathname;
    // Clear old charts if any
    activeCharts.forEach(c => c.destroy());
    activeCharts = [];

    if (path === '/' || path === '/dashboard') loadDashboard();
    else if (path === '/expenses') loadExpensesPage();
    else if (path === '/analytics') loadAnalyticsPage();
    else if (path === '/budget') loadBudgetPage();
}

/* --- AUTH --- */
async function login() {
    const u = document.getElementById("lUser").value;
    const p = document.getElementById("lPass").value;
    document.getElementById("authMsg").innerText = "";
    const res = await API.post("/api/login", { username: u, password: p });
    if (res && res.message === "Success") window.location.href = "/";
    else {
        document.getElementById("authMsg").innerText = res.error || "Failed";
        const msg = document.getElementById("authMsg"); msg.style.animation="none"; msg.offsetHeight; msg.style.animation="shake 0.5s";
    }
}

async function signup() {
    const u = document.getElementById("sUser").value;
    const e = document.getElementById("sEmail").value;
    const p = document.getElementById("sPass").value;
    document.getElementById("signupMsg").innerText = "";
    const res = await API.post("/api/signup", { username: u, email: e, password: p });
    if (res && res.message === "Created") { alert("Account created! Please login."); toggleAuth(); }
    else document.getElementById("signupMsg").innerText = res.error || "Failed";
}

async function logout() { await API.post("/api/logout"); window.location.href = "/login"; }
async function deleteAccount() { if(!confirm("Permanently delete account?")) return; await API.del("/api/delete_account"); window.location.href = "/login"; }
function toggleAuth() { document.getElementById('container').classList.toggle("right-panel-active"); }

/* --- PAGE LOGIC --- */
async function loadDashboard() {
    const [analytics, expenses] = await Promise.all([API.get("/api/analytics"), API.get("/api/expenses")]);
    if (!analytics) return;
    if(document.getElementById("totalSpent")) document.getElementById("totalSpent").innerText = fmt(analytics.total_spent);
    if(document.getElementById("monthlyBudget")) document.getElementById("monthlyBudget").innerText = fmt(analytics.budget);
    if(document.getElementById("remaining")) document.getElementById("remaining").innerText = fmt(analytics.budget - analytics.total_spent);
    const tbody = document.getElementById("recentTable");
    if (tbody) {
        if (expenses && expenses.length > 0) {
            tbody.innerHTML = expenses.slice(0, 5).map(e => `<tr><td>${e.title}</td><td>${fmt(e.amount)}</td><td>${e.category}</td><td>${e.date}</td></tr>`).join("");
        } else { tbody.innerHTML = "<tr><td colspan='4'>No recent expenses</td></tr>"; }
    }
}

async function loadExpensesPage() {
    const expenses = await API.get("/api/expenses");
    const tbody = document.getElementById("expTable");
    if (tbody) {
        if (expenses && expenses.length > 0) {
            tbody.innerHTML = expenses.map(e => `<tr><td>${e.title}</td><td>${fmt(e.amount)}</td><td>${e.category}</td><td>${e.date}</td><td><button class="btn btn-danger" onclick="deleteExpense('${e.id}')" style="padding:8px 12px; width:auto;">Delete</button></td></tr>`).join("");
        } else { tbody.innerHTML = "<tr><td colspan='5' style='text-align:center'>No expenses found.</td></tr>"; }
    }
    const dInput = document.getElementById("eDate");
    if(dInput) dInput.value = new Date().toISOString().split('T')[0];
}

async function addExpense() {
    const t = document.getElementById("eTitle").value;
    const a = document.getElementById("eAmount").value;
    const c = document.getElementById("eCat").value;
    const d = document.getElementById("eDate").value;
    if (!t || !a) return alert("Missing fields");
    const res = await API.post("/api/expenses", { title: t, amount: a, category: c, date: d });
    if (res && res.message) { document.getElementById("addForm").reset(); loadExpensesPage(); }
}

async function deleteExpense(id) { if (!confirm("Delete?")) return; await API.del(`/api/expenses/${id}`); loadExpensesPage(); }

async function loadAnalyticsPage() {
    const data = await API.get("/api/analytics");
    if (!data) return;
    const ctx1 = document.getElementById("catChart");
    const ctx2 = document.getElementById("trendChart");
    
    if (ctx1) {
        activeCharts.push(new Chart(ctx1, { type: 'doughnut', data: { labels: data.categories, datasets: [{ data: data.category_amounts, backgroundColor: ['#4A70A9', '#8FABD4', '#d9534f', '#f59e0b', '#10b981'] }] } }));
    }
    if (ctx2) {
        activeCharts.push(new Chart(ctx2, { type: 'bar', data: { labels: data.months, datasets: [{ label: 'Spend', data: data.monthly_amounts, backgroundColor: '#4A70A9' }] }, options: { scales: { y: { beginAtZero: true } } } }));
    }
}

async function loadBudgetPage() {
    const [b, a] = await Promise.all([API.get("/api/budget"), API.get("/api/analytics")]);
    if(document.getElementById("budgetInput")) document.getElementById("budgetInput").value = b.amount;
    const pct = b.amount > 0 ? Math.min(100, (a.total_spent / b.amount) * 100) : 0;
    if(document.getElementById("bSpent")) document.getElementById("bSpent").innerText = fmt(a.total_spent);
    if(document.getElementById("bTarget")) document.getElementById("bTarget").innerText = fmt(b.amount);
    if(document.getElementById("bBar")) document.getElementById("bBar").style.width = pct + "%";
}

async function saveBudget() {
    const val = document.getElementById("budgetInput").value;
    await API.put("/api/budget", { amount: val }); alert("Updated"); loadBudgetPage();
}

async function updateProfile() {
    const e = document.getElementById("pEmail").value;
    const p = document.getElementById("pPass").value;
    if (!e && !p) return alert("Nothing to update");
    const res = await API.put("/api/profile", { email: e, password: p });
    if (res && res.message) { alert("Updated"); window.location.reload(); }
}