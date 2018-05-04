import React from "react";
import { difference, filter, find, includes, map, some, sortBy, transform, get } from "lodash-es";
import { Col, Label, InputGroup, ListGroup, Modal, Panel, Row } from "react-bootstrap";
import { connect } from "react-redux";
import { push } from "react-router-redux";

import { listGroups, createGroup, setGroupPermission, removeGroup } from "../actions";
import { clearError } from "../../errors/actions";
import { AutoProgressBar, Button, Icon, InputError, ListGroupItem, LoadingPlaceholder } from "../../base";
import { routerLocationHasState } from "../../utils";

class Group extends React.Component {

    handleClick = () => {
        this.props.onSelect(this.props.id);
    };

    render () {
        const { id, active } = this.props;

        return (
            <ListGroupItem key={id} active={active} onClick={this.handleClick}>
                <span className="text-capitalize">
                    {id}
                </span>
            </ListGroupItem>
        );
    }

}

class Groups extends React.Component {

    constructor (props) {
        super(props);
        this.state = {
            activeId: null,
            createGroupId: "",
            spaceError: false,
            submitted: false,
            error: ""
        };
    }

    componentWillMount () {
        if (this.props.groups === null) {
            this.props.onList();
        } else if (this.props.groups.length) {
            this.setState({
                activeId: this.props.groups[0].id
            });
        }
    }

    componentWillReceiveProps (nextProps) {

        // If there are no groups, skip update
        if (!nextProps.groups.length) {
            return;
        }

        const state = {};

        // What to do if the active group was removed OR the active group id in state if onList response is incoming.
        if (!some(nextProps.groups, {id: this.state.activeId}) || (this.props.groups === null && nextProps.groups)) {
            state.activeId = nextProps.groups[0].id;
        }

        if (nextProps.groups.length > this.props.groups.length) {
            state.activeId = difference(nextProps.groups, this.props.groups)[0].id;
            state.createGroupId = "";
        }

        this.setState(state);
    }

    handleModalExited = () => {
        this.setState({
            createGroupId: "",
            spaceError: false,
            submitted: false,
            error: ""
        });

        this.props.updatePermissions();

        if (this.props.error) {
            this.props.onClearError("CREATE_GROUP_ERROR");
        }
    };

    handleSelect = (activeId) => {
        this.setState({
            activeId
        });
    };

    handleChange = (e) => {
        this.setState({
            createGroupId: e.target.value,
            spaceError: this.state.spaceError && includes(e.target.value, " "),
            submitted: false,
            error: ""
        });

        if (this.props.error) {
            this.props.onClearError("CREATE_GROUP_ERROR");
        }
    };

    handleSubmit = (e) => {
        e.preventDefault();

        if (this.state.createGroupId === "") {
            this.setState({
                error: "Group id missing"
            });
        } else if (includes(this.state.createGroupId, " ")) {
            this.setState({
                spaceError: true
            });
        } else {
            this.setState({submitted: true}, () => this.props.onCreate(this.state.createGroupId));
        }
    };

    render () {

        if (this.props.groups === null || this.props.users === null) {
            return <LoadingPlaceholder margin="130px" />;
        }

        let groupComponents = [];

        if (this.props.groups.length) {
            groupComponents = map(sortBy(this.props.groups, "id"), group =>
                <Group
                    key={group.id}
                    {...group}
                    active={this.state.activeId === group.id}
                    onSelect={this.handleSelect}
                />
            );
        }

        const activeGroup = find(this.props.groups, {id: this.state.activeId});
        let members = [];

        if (activeGroup) {
            members = filter(this.props.users, user => includes(user.groups, activeGroup.id));
        }

        let memberComponents = [];

        if (members.length) {
            memberComponents = map(members, member =>
                <Label key={member.id} style={{marginRight: "5px"}}>
                    {member.id}
                </Label>
            );
        }

        if (!memberComponents.length) {
            memberComponents = (
                <div className="text-center">
                    <Icon name="info" /> No members found.
                </div>
            );
        }

        let error;

        if (this.state.submitted && this.props.error) {
            error = this.props.error;
        }

        if (this.state.spaceError) {
            error = "Group names may not contain spaces";
        }

        let permissionComponents = [];

        if (activeGroup) {
            permissionComponents = transform(activeGroup.permissions, (result, value, key) => {

                result.push(
                    <ListGroupItem
                        key={key}
                        onClick={() => this.props.onSetPermission(activeGroup.id, key, !value)}
                    >
                        <code>{key}</code> <Icon faStyle="far" name={value ? "check-square" : "square"} pullRight />
                    </ListGroupItem>
                );

                return result;
            }, []);
        }

        return (
            <Modal show={this.props.show} onHide={this.props.onHide} onExited={this.handleModalExited}>
                <Modal.Header onHide={this.props.onHide} closeButton>
                    Groups
                </Modal.Header>

                <AutoProgressBar active={this.props.pending} affixed />

                <Modal.Body>
                    <Row>
                        <Col md={5}>
                            <InputGroup>
                                <InputError
                                    type="text"
                                    value={this.state.createGroupId}
                                    onChange={this.handleChange}
                                    error={error || this.state.error}
                                />
                                <InputGroup.Button style={{verticalAlign: "top", zIndex: "0"}}>
                                    <Button type="button" bsStyle="primary" onClick={this.handleSubmit}>
                                        <Icon name="plus-square" style={{verticalAlign: "middle", marginLeft: "3px"}} />
                                    </Button>
                                </InputGroup.Button>
                            </InputGroup>
                            <br />
                            <ListGroup>
                                {groupComponents}
                            </ListGroup>
                        </Col>
                        <Col md={7}>
                            <Panel>
                                <Panel.Heading>Permissions</Panel.Heading>
                                <ListGroup>
                                    {permissionComponents}
                                </ListGroup>
                            </Panel>

                            <Panel>
                                <Panel.Heading>Members</Panel.Heading>
                                <Panel.Body>
                                    {memberComponents}
                                </Panel.Body>
                            </Panel>

                            <Button
                                icon="remove"
                                bsStyle="danger"
                                onClick={() => this.props.onRemove(activeGroup.id)}
                                block
                            >
                                Remove Group
                            </Button>
                        </Col>
                    </Row>
                </Modal.Body>
            </Modal>
        );
    }
}

const mapStateToProps = (state) => ({
    show: routerLocationHasState(state, "groups"),
    users: state.users.list,
    groups: state.groups.list,
    pending: state.groups.pending,
    error: get(state, "errors.CREATE_GROUP_ERROR.message", "")
});

const mapDispatchToProps = (dispatch) => ({

    onCreate: (groupId) => {
        dispatch(createGroup(groupId));
    },

    onHide: () => {
        dispatch(push({...window.location, state: {groups: false}}));
    },

    onList: () => {
        dispatch(listGroups());
    },

    onRemove: (groupId) => {
        dispatch(removeGroup(groupId));
    },

    onSetPermission: (groupId, permission, value) => {
        dispatch(setGroupPermission(groupId, permission, value));
    },

    onClearError: (error) => {
        dispatch(clearError(error));
    }

});

export default connect(mapStateToProps, mapDispatchToProps)(Groups);
