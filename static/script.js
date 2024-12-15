document.addEventListener("DOMContentLoaded", () => {
  const recordButton = document.getElementById("recordButton");
  const analyzeButton = document.getElementById("analyzeButton");
  const userInput = document.getElementById("userInput");
  const languageSelect = document.getElementById("languageSelect");
  const sentimentGraph = document.getElementById("sentimentGraph");

  // Initialisation de la reconnaissance vocale
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const recognition = SpeechRecognition ? new SpeechRecognition() : null;

  if (!recognition) {
    alert("Votre navigateur ne supporte pas la reconnaissance vocale.");
    recordButton.disabled = true;
  } else {
    languageSelect.addEventListener("change", () => {
      const selectedLanguage = languageSelect.value;
      recognition.lang = selectedLanguage;
      console.log("Langue de reconnaissance définie sur :", selectedLanguage);
    });

    recognition.lang = languageSelect.value;

    recognition.onstart = () => {
      recordButton.textContent = "Écoute en cours...";
    };

    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      userInput.value = transcript;
      recordButton.textContent = "🎤 Enregistrer";
    };

    recognition.onerror = () => {
      recordButton.textContent = "🎤 Enregistrer";
      alert("Erreur lors de la reconnaissance vocale.");
    };

    recognition.onend = () => {
      recordButton.textContent = "🎤 Enregistrer";
    };

    recordButton.addEventListener("click", () => {
      recognition.start();
    });
  }

  analyzeButton.addEventListener("click", async () => {
    const text = userInput.value.trim();
    if (!text) {
      alert("Veuillez saisir ou enregistrer un texte avant d'analyser.");
      return;
    }

    // Appel au backend Flask pour l'analyse
    try {
      const response = await fetch("/analyze", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ text }),
      });
      const data = await response.json();
      displayResults(data);
    } catch (error) {
      console.error("Erreur lors de l'analyse :", error);
    }
  });

  function displayResults(data) {
    sentimentGraph.innerHTML = ""; // Clear previous graph

    // Résumé des sentiments (positif, négatif, neutre)
    const sentimentScores = data.sentimentScores;

    // Identifier le sentiment dominant
    let dominantSentiment = "neutre"; // Valeur par défaut
    if (sentimentScores.positive >= sentimentScores.negative && sentimentScores.positive >= sentimentScores.neutral) {
        dominantSentiment = "positif";
    } else if (sentimentScores.negative >= sentimentScores.positive && sentimentScores.negative >= sentimentScores.neutral) {
        dominantSentiment = "négatif";
    }

    // Appeler displayEmotion pour afficher l'icône correspondante
    displayEmotion(dominantSentiment);

    // Préparer les données pour Chart.js
    const chartData = {
        labels: ["Positif", "Négatif", "Neutre"],
        datasets: [
            {
                label: "Répartition des Sentiments",
                data: [
                    sentimentScores.positive * 100,
                    sentimentScores.negative * 100,
                    sentimentScores.neutral * 100,
                ],
                backgroundColor: ["#4caf50", "#f44336", "#ffc107"], // Couleurs des segments
            },
        ],
    };

    // Options du graphique
    const chartOptions = {
        responsive: true,
        plugins: {
            legend: {
                display: true,
                position: "top",
            },
        },
    };

    // Créer un canvas pour Chart.js
    const canvas = document.createElement("canvas");
    sentimentGraph.appendChild(canvas);

    // Initialiser le graphique
    new Chart(canvas.getContext("2d"), {
        type: "pie", // Changer en 'bar' pour un diagramme en barres
        data: chartData,
        options: chartOptions,
    });
}

});





