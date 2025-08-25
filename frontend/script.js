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
    resultDiv.innerHTML = ""; // clear old results

    // Display counts
    resultDiv.innerHTML += `
        <p>Total Stocks: ${data.count.total}</p>
        <p>Eligible: ${data.count.eligible} | Rejected: ${data.count.rejected}</p>
    `;

    // Display Eligible Table
    if (data.eligible.length > 0) {
        resultDiv.innerHTML += "<h3>Eligible Stocks</h3>";
        resultDiv.innerHTML += createTable(data.eligible);
    } else {
        resultDiv.innerHTML += "<h3>Eligible Stocks</h3><p>None</p>";
    }

    // Display Rejected Table
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
                    option.value = item.list_name;        // value for form/backend
                    option.textContent = item.list_name;  // what user sees
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

    // Keep keys same as your HTML option values (case sensitive)
    const algorithms = {
        Bullish: ["Shooting Star"],
        Bearish: ["Algorithm X", "Algorithm Y"],
    };

    function updateAlgorithms() {
        // Clear old options
        algoSelect.innerHTML = "";

        // Always add default "Select"
        const defaultOption = document.createElement("option");
        defaultOption.text = "Select";
        defaultOption.value = "selector";
        algoSelect.add(defaultOption);

        // Get selected trend
        const selectedTrend = trendSelect.value;

        // If trend exists in our object, add its algorithms
        if (algorithms[selectedTrend]) {
            algorithms[selectedTrend].forEach(algo => {
                const option = document.createElement("option");
                option.text = algo;
                option.value = algo.toLowerCase().replace(/\s+/g, "");
                algoSelect.add(option);
            });
        }
    }

    // Run once on load so dropdown is initialized
    updateAlgorithms();

    // Run again whenever trend changes
    trendSelect.addEventListener("change", updateAlgorithms);
});




        // function loadStocks() {
        //     fetch(`http://127.0.0.1:5000/api/stocks`)
        //         .then(response => response.json())
        //         .then(stocks => {
        //             const container = document.getElementById('table');
        //             if (stocks.length === 0) {
        //                 container.innerHTML = '<p>No stock is found</p>';
        //                 return;
        //             }
        //             let html = '<table border="1" cellpadding="8" cellspacing="0">';
        //             html += '<thead><tr><th>Stock Name</th><th>Trading Symbol</th></tr></thead><tbody>';
        //             stocks.forEach(stock => {
        //                 html += `<tr><td>${stock.stock_name}</td><td>${stock.tradingsymbol}</td></tr>`;
        //             });
        //             html += '</tbody></table>';
        //             container.innerHTML = html;
        //         })
        //         .catch(err => {
        //             document.getElementById('table').innerHTML = 'Error loading stocks';
        //             console.error(err);
        //         });
        // }

        // window.onload = loadStocks;