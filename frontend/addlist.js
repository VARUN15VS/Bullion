document.getElementById("searchButton").addEventListener("click", async () => {
    const stock = document.getElementById("search").value.trim();
    const resultDiv = document.querySelector(".result");

    if (!stock) {
        resultDiv.innerHTML = "<p>Please enter a stock name.</p>";
        return;
    }

    try {
        const res = await fetch("/search", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ stock })
        });

        const data = await res.json();
        if (!data.found) {
            resultDiv.innerHTML = `<p>No stock found</p>`;
        } else {
            const color = data.price >= data.last_close ? "green" : "red";
            resultDiv.innerHTML = `
                <div>
                    <p><strong>${data.name}</strong></p>
                    <p style="color:${color}">Current Price: ₹${data.price}</p>
                    <p>Last Close: ₹${data.last_close}</p>
                    <button class="add-btn">Add</button>
                </div>
            `;
        }
    } catch (err) {
        console.error(err);
        resultDiv.innerHTML = "<p>Error fetching stock data.</p>";
    }
});
