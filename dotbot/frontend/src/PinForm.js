import './PinForm.css';

const PinForm = ({ pinUpdate }) => {

  const onInputPinChange = (event) => {
    if (event.target.value.length === parseInt(process.env.REACT_APP_PIN_CODE_LENGTH)) {
      pinUpdate(event.target.value);
    }
  };

  return (
    <>
    <div className="container">
      <form id="pin-code-input">
        <p>Enter pin code:</p>
        <p>
          <input type="password" className="form-control" autoFocus="autofocus" onChange={(event) => onInputPinChange(event)} />
        </p>
      </form>
    </div>
    </>
  );
};

export default PinForm;
