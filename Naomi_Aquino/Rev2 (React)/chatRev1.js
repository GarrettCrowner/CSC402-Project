/* React Concepts
useState = React's "short-term memory" hook that triggers a UI refresh when data changes.
JSX = A syntax that looks like HTML but lives inside JavaScript (the code you see above).
map() = The "looper" tool that takes your message history and turns it into a list of bubbles.
Props = "Properties" passed from one component to another (like giving a name to a bubble).
Hooks = Special functions (like useEffect) that handle side-effects like auto-scrolling.
*/

// Grab hooks from the global React object provided by the CDN
// 1. Grab the Hooks from the global React object (Provided by the CDN)
const { useState, useEffect, useRef } = React;

function App() {
    // 2. Memory (State): This replaces your old 'Agent' object variables
    const [messages, setMessages] = useState([
        { role: "assistant", content: "Hi, my name is Rammy. I am here to help with all of your HR questions! What would you like to know?" }
    ]);
    const [userInput, setUserInput] = useState("");
    const [isTyping, setIsTyping] = useState(false);
    
    // 3. Pointer: This replaces your old 'chatWindow' variable for scrolling
    const chatEndRef = useRef(null);

    // 4. Auto-Scroll: Runs every time 'messages' or 'isTyping' changes
    useEffect(() => {
        chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages, isTyping]);

    // 5. Chat Logic: This replaces 'handleChat' and 'Agent.send'
    const handleSend = async () => {
        if (userInput.trim() === "") return;

        const textToSend = userInput;
        setUserInput(""); // Clear input immediately

        // Show User Message
        const newHistory = [...messages, { role: "user", content: textToSend }];
        setMessages(newHistory);
        
        // Show "Typing"
        setIsTyping(true);

        // Simulate API/Thinking Delay
        await new Promise(resolve => setTimeout(resolve, 2000));

        // Show Rammy's Response
        const botReply = "Your message was received!";
        setMessages([...newHistory, { role: "assistant", content: botReply }]);
        setIsTyping(false);
    };
    /* Pending API logic (Replaces step 5)
    try {
        const response = await fetch("https://api.openai.com", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer YOUR_API_KEY` // Replace with your key
            },
            body: JSON.stringify({
                model: "gpt-3.5-turbo",
                // Logic: Send the existing history so Rammy remembers previous questions
                messages: newHistory.map(m => ({
                    role: m.role === "user" ? "user" : "assistant",
                    content: m.content
                }))
            })
        });

        const data = await response.json();
        const botReply = data.choices[0].message.content;

        // 3. Update UI with AI Response
        setMessages([...newHistory, { role: "assistant", content: botReply }]);

    } catch (error) {
        console.error("API Error:", error);
        setMessages([...newHistory, { role: "assistant", content: "Sorry, I'm having trouble connecting right now." }]);
    } finally {
        setIsTyping(false); // Always hide the loading bubble at the end
    }
    */

    // 6. The UI: This is your HTML structure converted to JSX
    return (
        <div className="chat-window" style={{ width: '400px', margin: '0 auto' }}>
            {/* 1. Header Section (Converted from HTML) */}
            <header id="chat-header">
                <button id="chat-close-btn" onClick={() => console.log("Close Clicked")}>
                     <ion-icon name="close-outline"></ion-icon>
                </button>
                <h2>Ask Rammy</h2>
                <button id="chat-options-btn" onClick={() => console.log("Options Clicked")}>
                    <ion-icon name="ellipsis-vertical-circle-outline"></ion-icon>
                </button>
            </header>

            {/* 2. Message Display Area (Main Container) */}
            <main id="message-container">
                {/* Loop through messages array */}
                {messages.map((msg, index) => (
                    <div key={index} className={`${msg.role === "user" ? "user" : "agent"}-msg-wrapper`}>
                        <div className={`${msg.role === "user" ? "user" : "agent"}-bubble`}>
                            <p>{msg.content}</p>
                        </div>
                        <span className="profile-name">
                            {msg.role === "user" ? "You" : "Rammy"}
                        </span>
                    </div>
                ))}
            {/* Loading Indicator (Only shows when isTyping is true) */}
                {isTyping && (
                    <div className="agent-msg-wrapper">
                        <div className="loading-bubble typing-indicator">
                            <p>typing...</p>
                        </div>
                    </div>
                )}
                
                {/* Invisible anchor for the scroll pointer */}
                <div ref={chatEndRef} />
            </main>     

            {/* 3. Input Area (Converted from HTML Footer) */}
            <footer id="chat-footer">
                <form 
                    id="chat-user-form" 
                    onSubmit={(e) => {
                        e.preventDefault(); // Logic: Prevents the page from refreshing
                        handleSend();       // Trigger: Calls your existing chat logic
                    }}
                >
                    <input 
                        type="text" 
                        id="chat-user-input" 
                        placeholder="Ask a question..." 
                        required 
                        value={userInput} // Controlled Component: Linked to React State
                        onChange={(e) => setUserInput(e.target.value)} // Sync: Updates state as you type
                    />
                    <button type="submit" id="send-btn">
                        <ion-icon name="send"></ion-icon>
                    </button>
                </form>
            </footer>
        </div>
    );
}

// 7. Ignition: Start React and point it to the <div id="root">
const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);
