const fetch_dotbots = () => {
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
};

const make_active = (address) => {
    fetch(`http://localhost:8000/controller/dotbots/${address}`, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json',
        },
    })
    .then((response) => {
        response.json()
    })
    .catch((error) => {
        console.error("Error:", error);
    });
};

const populate_table = (dotbots) => {
    let index = 0;
    let table = document. getElementById("table");

    let tbody = table.getElementsByTagName('tbody')[0];
    tbody.innerHTML = "";
    dotbots.forEach(dotbot => {
        let row = tbody.insertRow(index)
        row.innerHTML = `
            <td>0x${dotbot.address}</td>
            <td>${dotbot.last_seen.toFixed(3)}</td>
            <td><button class="btn btn-outline-light" onclick="make_active('${dotbot.address}');">${dotbot.active}</button></td>`
        index++;
    });
};

window.addEventListener("load", fetch_dotbots);
