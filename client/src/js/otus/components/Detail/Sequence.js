import PropTypes from "prop-types";
import React from "react";
import { connect } from "react-redux";
import { Collapse } from "react-bootstrap";
import styled from "styled-components";
import { Badge, BoxGroupSection, Icon, InfoLabel, Label, Table } from "../../../base";
import { followDownload } from "../../../utils/utils";

const SequenceHeader = styled.div`
    align-items: center;
    display: flex;
`;

const SequenceHeaderButtons = styled.span`
    align-items: center;
    display: flex;
    margin-left: auto;

    button {
        margin-left: 2px;
    }

    i.fas {
        margin-right: 3px;
    }
`;

const SequenceHeaderDefinition = styled.span`
    margin-left: 7px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
`;

const SequenceTable = styled(Table)`
    margin-top: 10px;
`;

class Sequence extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            in: false
        };
    }

    static propTypes = {
        id: PropTypes.string,
        accession: PropTypes.string,
        definition: PropTypes.string,
        host: PropTypes.string,
        segment: PropTypes.string,
        sequence: PropTypes.string,
        showEditSequence: PropTypes.func,
        showRemoveSequence: PropTypes.func,
        canModify: PropTypes.bool,
        dataType: PropTypes.string
    };

    handleCloseClick = () => {
        this.setState({ in: false });
    };

    handleDownload = () => {
        followDownload(`/download/sequences/${this.props.id}`);
    };

    handleShowEditSequence = () => {
        this.props.showEditSequence(this.props.id);
    };

    handleShowRemoveSequence = () => {
        this.props.showRemoveSequence(this.props.id);
    };

    render() {
        const accession = this.props.accession;

        let buttons;

        if (this.state.in) {
            buttons = (
                <SequenceHeaderButtons>
                    {this.props.canModify ? (
                        <Icon
                            name="pencil-alt"
                            bsStyle="warning"
                            tip="Edit Sequence"
                            onClick={this.handleShowEditSequence}
                        />
                    ) : null}
                    {this.props.canModify ? (
                        <Icon
                            name="trash"
                            bsStyle="danger"
                            tip="Remove Sequence"
                            onClick={this.handleShowRemoveSequence}
                        />
                    ) : null}
                    <Icon name="download" tip="Download FASTA" onClick={this.handleDownload} />
                    <button type="button" className="close" onClick={this.handleCloseClick}>
                        <span>×</span>
                    </button>
                </SequenceHeaderButtons>
            );
        }

        let segment;

        if (!this.state.in && this.props.segment) {
            segment = <InfoLabel className="text-mono">{this.props.segment}</InfoLabel>;
        }
        const SegmentRow = () => {
            if (this.props.dataType === "barcode") {
                return null;
            }
            return (
                <tr>
                    <th>Segment</th>
                    <td>{segment}</td>
                </tr>
            );
        };
        return (
            <BoxGroupSection onClick={this.state.in ? null : () => this.setState({ in: true })}>
                <SequenceHeader>
                    <Label>{accession}</Label>
                    <SequenceHeaderDefinition>{this.props.definition}</SequenceHeaderDefinition>
                    {segment}
                    {buttons}
                </SequenceHeader>
                <Collapse in={this.state.in}>
                    <div>
                        <SequenceTable>
                            <tbody>
                                <tr>
                                    <th>Accession</th>
                                    <td>{accession}</td>
                                </tr>
                                <tr>
                                    <th>Definition</th>
                                    <td>{this.props.definition}</td>
                                </tr>
                                <SegmentRow />
                                <tr>
                                    <th>Host</th>
                                    <td>{this.props.host}</td>
                                </tr>

                                <tr>
                                    <th>
                                        Sequence <Badge>{this.props.sequence.length}</Badge>
                                    </th>
                                    <td className="sequence-cell">
                                        <textarea rows="5" value={this.props.sequence} readOnly />
                                    </td>
                                </tr>
                            </tbody>
                        </SequenceTable>
                    </div>
                </Collapse>
            </BoxGroupSection>
        );
    }
}

const mapStateToProps = state => ({
    dataType: state.references.detail.data_type
});
export default connect(mapStateToProps)(Sequence);
