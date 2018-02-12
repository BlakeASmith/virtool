import React from "react";
import PropTypes from "prop-types";
import { Modal } from "react-bootstrap";
import { Button } from "../../../base";
import { reject } from "lodash-es";
import { connect } from "react-redux";

class RemoveSegment extends React.Component {

    handleSubmit = (e) => {
        e.preventDefault();

        let newArray = this.props.schema.slice();
        newArray = reject(newArray, ["name", this.props.curSeg.name]);

        this.props.onSubmit(newArray);
    }

    render () {

        return (
            <Modal
                show={this.props.show}
                onExited={this.handleExited}
                dialogClassName="modal-danger"
                onHide={this.props.onHide}
            >
                <Modal.Header closeButton>
                    Remove Segment
                </Modal.Header>
                <Modal.Body>
                    Are you sure you want to remove the segment <strong>{this.props.curSeg.name}</strong>?
                </Modal.Body>
                <Modal.Footer>
                    <Button
                        bsStyle="danger"
                        icon="checkmark"
                        onClick={this.handleSubmit}
                    >
                        Confirm
                    </Button>
                </Modal.Footer>
            </Modal>
        );
    }
}

RemoveSegment.propTypes = {
    schema: PropTypes.arrayOf(PropTypes.object),
    show: PropTypes.bool.isRequired,
    onHide: PropTypes.func,
    onSubmit: PropTypes.func,
    curSeg: PropTypes.shape({
        name: PropTypes.string,
        molecule: PropTypes.string,
        required: PropTypes.bool
    }).isRequired
};

const mapStateToProps = (state) => ({
    schema: state.viruses.detail.schema
});

export default connect(mapStateToProps)(RemoveSegment);
