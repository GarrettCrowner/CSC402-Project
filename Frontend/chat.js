/* Notes
const = constant. A permananent var
async = asychronous. Alerts js that this function will buffer.
await = Pauses code for 800ms. Simulates a thinking phase for the chat agent.
this = calling the const. (In this case, Agent).
new Promise = Object representing the attempt of an async operation
return = Exits a function, and sends its value back to the user
resolve = Tells Promise to complete function
window.onload = A "startup" trigger that runs code as soon as the page finishes loading.
trim() = A tool that removes accidental empty spaces from the start/end of a text string.
? (Optional Chaining) = A safety check that only runs a command if an element exists.

DOM Terms (Web APIs)
document = Master object
getElementById() = Grabs an element
addEventListener() = Waits for user action
createElement() = Creates a new HTML tag
innerHTML = Change the text inside an element
appendChild() = Sticks new element inside another one
scrollTop = auto scrolls to the newest message
scrollHeight = Total height of the content inside a box
value = Get the text typed into an <input> field
setTimeout() = Timer that waits a given number of ms
className = A property used to give an element a CSS class (for styling).
textContent = A secure way to add plain text to a bubble (ignores HTML tags).
remove() = The "eraser" command that deletes an element (used for the dots).

Logic & Memory
parentElement = Reaches "up" one level to find the container holding a bubble.
Template Literals = The `${variable}` syntax used to plug data directly into HTML.
push() = Adds a new message to the end of the history list.
*/

/* Pending concerns
- Simulating the chatbox to open as a new window from the chat button on the website
- Ingesting the API logic (Simulated logic)
- No use of React UI as of now (Will be needed to stream the input of the agent text, and handle long conversations)
- Adding time stamps and profile cards and names
*/

const chatWindow = document.getElementById('message-container');
const inputField = document.getElementById('chat-user-input');
const sendBtn = document.getElementById('send-btn');

/* API links (TBD)
const API_URL = "https://api.openai.com/v1/chat/completions";
const API_KEY = "your-api-key-here";
*/

const Agent = {
    name: "Rammy",
    history: [],

    displayMessage(role, text) {
        // 1. Wrap bubble and tag
        const messageWrapper = document.createElement('div');
        messageWrapper.className = (role === "You") ? "user-msg-wrapper" : "agent-msg-wrapper";

        // 2. Create bubble
        const newBubble = document.createElement('div');
        
        // Add loading effect
        if (role === "Typing") {
            newBubble.className = "agent-bubble typing-indicator";
            newBubble.id = "loading-bubble"; 
            newBubble.innerHTML = `<div class="dot"></div><div class="dot"></div><div class="dot"></div>`;
        } else {
            newBubble.className = (role === "You") ? "user-bubble" : "agent-bubble";
            newBubble.innerHTML = `<p>${text}</p>`;
        }

        // 3. Add bubble to wrapper
        messageWrapper.appendChild(newBubble);

        // 4. Create name tag, and add to wrapper
        if (role !== "Typing") {
            const nameTag = document.createElement('span');
            nameTag.className = "profile-name";
            nameTag.textContent = (role === "You") ? "You" : this.name;
            messageWrapper.appendChild(nameTag);
        }
        
        // 5. Add the wrapper to the chat
        chatWindow.appendChild(messageWrapper);
        chatWindow.scrollTop = chatWindow.scrollHeight;
    },
    
    async send(text) {
        // 1. Log user message to memory and print it
        this.history.push({ role: "user", content: text });
        this.displayMessage("You", text);

        // 2. Print the loading bubble
        this.displayMessage("Typing", "");
        
        // 3. Buffer the agent processing
        await new Promise(resolve => setTimeout(resolve, 2000)); // Creates delay. Simulates the agent processing

        // 4. Simulate print of the agent bubble
        const reply = "Your message was received"; 
        /* Pedning API Logic (Replaces above line)
        let reply = "";
        try {
            const response = await fetch("https://api.openai.com", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer YOUR_API_KEY` // Your secret key
                },
                body: JSON.stringify({
                    model: "gpt-3.5-turbo",
                    messages: this.history // Sends the whole conversation for memory!
                })
            });

            const data = await response.json();
            reply = data.choices[0].message.content; // Grabs the AI's words

        } catch (error) {
            console.error("Connection Error:", error);
            reply = "Sorry, my brain hit a snag. Can you try again?";
        }
         */

        this.history.push({ role: "assistant", content: reply });

        // 5. Transform the loading bubble into the agent bubble
        const loader = document.getElementById("loading-bubble");
        if (loader) {
            const parent = loader.parentElement; 

            // Clears loading id, changes it to the agent id
            loader.id = ""; 
            loader.className = "agent-bubble"; 
            loader.innerHTML = `<p>${reply}</p>`; 

            // 2. Add the agent tag manually
            const nameTag = document.createElement('span');
            nameTag.className = "profile-name";
            nameTag.textContent = this.name;
            parent.appendChild(nameTag);

            chatWindow.scrollTop = chatWindow.scrollHeight;
        }
    }
};

// 1. Function to grab the input and tell the Agent to send it
async function handleChat() {
    const text = inputField.value.trim(); // Get text & remove extra spaces
    if (text !== "") {
        inputField.value = ""; // Clear the box for the next message
        await Agent.send(text); // Respects delay. Records message in history
    }
}

window.onload = () => {
    // This triggers as soon as the page finishes loading
    const welcomeText = "Hi, my name is Rammy. I am here to help with all of your HR questions! What would you like to know?";
    
    // 1. Record it in memory
    Agent.history.push({ role: "assistant", content: welcomeText });
    
    // 2. Show it on screen (The name tag "Rammy" will appear automatically)
    Agent.displayMessage("Agent", welcomeText);
};


// 2. Link the button click to that function
sendBtn.addEventListener('click', handleChat);

