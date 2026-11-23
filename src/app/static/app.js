const input = document.querySelector("#attachment");
const name = document.querySelector("#file-name");

if (input && name) {
  input.addEventListener("change", () => {
    name.textContent = input.files.length ? input.files[0].name : "No file selected";
  });
}