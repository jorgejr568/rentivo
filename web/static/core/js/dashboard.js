(function () {
  if (typeof Chart === "undefined") return;

  function brl(cents) {
    return (cents / 100).toLocaleString("pt-BR", {
      style: "currency",
      currency: "BRL",
    });
  }

  var monthly = document.getElementById("dashboard-monthly-chart");
  if (monthly) {
    var series = JSON.parse(monthly.dataset.series || "[]");
    new Chart(monthly, {
      type: "bar",
      data: {
        labels: series.map(function (p) { return p.reference_month; }),
        datasets: [
          {
            label: "Faturado",
            data: series.map(function (p) { return p.faturado_cents / 100; }),
            backgroundColor: "#0d6efd",
          },
          {
            label: "Recebido",
            data: series.map(function (p) { return p.recebido_cents / 100; }),
            backgroundColor: "#198754",
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: {
            beginAtZero: true,
            ticks: { callback: function (v) { return brl(v * 100); } },
          },
        },
        plugins: {
          tooltip: { callbacks: { label: function (ctx) { return ctx.dataset.label + ": " + brl(ctx.parsed.y * 100); } } },
        },
      },
    });
  }

  var status = document.getElementById("dashboard-status-chart");
  if (status) {
    var counts = JSON.parse(status.dataset.counts || "[]");
    new Chart(status, {
      type: "doughnut",
      data: {
        labels: counts.map(function (c) { return c.status; }),
        datasets: [{ data: counts.map(function (c) { return c.count; }) }],
      },
      options: { responsive: true, maintainAspectRatio: false },
    });
  }
})();
