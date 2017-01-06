/**
 * @license
 * The MIT License (MIT)
 * Copyright 2015 Government of Canada
 *
 * @author
 * Ian Boyes
 *
 * @exports Task
 */

import React from "react";
import { includes } from "lodash";
import { Row, Col } from "react-bootstrap";
import { ListGroupItem } from "virtool/js/components/Base";
import { getTaskDisplayName } from "virtool/js/utils";

import TaskField from "./TaskField";

/**
 * A ListGroupItem-based form component that allows editing of task-specific resource limits in form child components.
 */
const Task = (props) => {

    const readOnly = includes(["add_host", "rebuild_index"], props.taskPrefix);

    return (
        <ListGroupItem allowFocus>
            <h5><strong>{getTaskDisplayName(props.taskPrefix)}</strong></h5>
            <Row>
                <Col md={4}>
                    <TaskField
                        {...props}
                        resource="proc"
                        readOnly={readOnly}
                    />
                </Col>
                <Col md={4}>
                    <TaskField
                        {...props}
                        resource="mem"
                        readOnly={readOnly}
                    />
                </Col>
                <Col md={4}>
                    <TaskField
                        {...props}
                        resource="inst"
                        readOnly={props.taskPrefix === "rebuild_index"}
                    />
                </Col>
            </Row>
        </ListGroupItem>
    );
};

Task.propTypes = {
    set: React.PropTypes.func,
    settings: React.PropTypes.object,
    taskPrefix: React.PropTypes.string.isRequired
};

export default Task;
