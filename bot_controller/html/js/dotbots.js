function fetch_dotbots() {
    console.log("fetching dotbots")

    fetch("http://localhost:8000/controller/dotbots")
    .then(function(response) {
        if (response.ok) {
            response.json().then(function(data) {
                populate_table(data);
                setTimeout(() => fetch_dotbots(), 1000);
            });
        } else {
            console.log("Network failure");
        }
    })
    .catch(function(error) {
        console.log(`Failed to fetch dotbots: ${error.message}`);
    });
}

function populate_table(dotbots) {
    let index = 1;
    let table = document. getElementById("table");

    for (let row_idx = 1; row_idx < table.rows.length; row_idx++) {
        table.deleteRow(row_idx);
    }
    dotbots.forEach(dotbot => {
        console.log(dotbot.address);
        let row = table.insertRow(index)
        row.innerHTML = `
            <td>0x${dotbot.address}</td>
            <td>${dotbot.last_seen}</td>
            <td>${dotbot.active}</td>`
        index++;
    });
}
