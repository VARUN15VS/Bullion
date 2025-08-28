document.getElementById("startBtn").addEventListener("click", () => {
    const trend = document.getElementById("trend").value;
    const algorithm = document.getElementById("algorithm").value;
    const list = document.getElementById("list").value;

    if (trend === "selector" || algorithm === "selector" || list === "selector") {
        alert("Please select all options!");
        return;
    }

    fetch("http://127.0.0.1:5005/api/shooting_star", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ list })
    })
    .then(res => res.json())
    .then(data => {
        displayResults(data);
    })
    .catch(err => {
        console.error("Error:", err);
    });
});

function displayResults(data) {
    const resultDiv = document.querySelector(".result");
    resultDiv.innerHTML = ""; 

    resultDiv.innerHTML += `
        <p>Total Stocks: ${data.count.total}</p>
        <p>Eligible: ${data.count.eligible} | Rejected: ${data.count.rejected}</p>
    `;

    if (data.eligible.length > 0) {
        resultDiv.innerHTML += "<h3>Eligible Stocks</h3>";
        resultDiv.innerHTML += createTable(data.eligible);
    } else {
        resultDiv.innerHTML += "<h3>Eligible Stocks</h3><p>None</p>";
    }

    if (data.rejected.length > 0) {
        resultDiv.innerHTML += "<h3>Rejected Stocks</h3>";
        resultDiv.innerHTML += createTable(data.rejected);
    } else {
        resultDiv.innerHTML += "<h3>Rejected Stocks</h3><p>None</p>";
    }
}

function createTable(arrayData) {
    if (!Array.isArray(arrayData) || arrayData.length === 0) return "<p>No data</p>";

    let table = "<table border='1' cellpadding='8' cellspacing='0'>";
    table += "<tr>";
    Object.keys(arrayData[0]).forEach(key => {
        table += `<th>${key.toUpperCase()}</th>`;
    });
    table += "</tr>";

    arrayData.forEach(item => {
        table += "<tr>";
        Object.values(item).forEach(val => {
            table += `<td>${val}</td>`;
        });
        table += "</tr>";
    });

    table += "</table>";
    return table;
}



window.onload = function() {
    fetch('http://127.0.0.1:5000/api/lists')
        .then(response => response.json())
        .then(data => {
            const dropdown = document.getElementById('list');
            dropdown.innerHTML = ''; 

            if (data.length === 0) {
                dropdown.innerHTML = '<option>No lists available</option>';
            } else {
                data.forEach(item => {
                    const option = document.createElement('option');
                    option.value = item.list_name;
                    option.textContent = item.list_name;
                    dropdown.appendChild(option);
                });
            }
        })
        .catch(err => {
            console.error('Error loading dropdown:', err);
            document.getElementById('list').innerHTML = '<option>Error loading</option>';
        });
};


document.addEventListener("DOMContentLoaded", () => {
    const trendSelect = document.getElementById("trend");
    const algoSelect = document.getElementById("algorithm");

    const algorithms = {
        Bullish: ["Algorithm X", "Algorithm Y"],
        Bearish: ["Shooting Star"],
    };

    function updateAlgorithms() {
        algoSelect.innerHTML = "";

        const defaultOption = document.createElement("option");
        defaultOption.text = "Select";
        defaultOption.value = "selector";
        algoSelect.add(defaultOption);

        const selectedTrend = trendSelect.value;

        if (algorithms[selectedTrend]) {
            algorithms[selectedTrend].forEach(algo => {
                const option = document.createElement("option");
                option.text = algo;
                option.value = algo.toLowerCase().replace(/\s+/g, "");
                algoSelect.add(option);
            });
        }
    }

    updateAlgorithms();

    trendSelect.addEventListener("change", updateAlgorithms);
});