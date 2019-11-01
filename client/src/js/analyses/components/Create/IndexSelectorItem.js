import React, { useCallback } from "react";
import { Label } from "react-bootstrap";
import styled from "styled-components";
import { Checkbox, ListGroupItem } from "../../../base";

const StyledIndexSelectorItem = styled(ListGroupItem)`
    align-items: center;
    display: flex;
    justify-content: space-between;

    .label {
        margin-left: 3px;
    }

    span {
        align-items: center;
        display: flex;
    }

    strong {
        margin-left: 8px;
    }
`;

export const IndexSelectorItem = ({ id, reference, isSelected, version, onSelect }) => {
    const handleClick = useCallback(() => onSelect({ id, refId: reference.id }), []);

    return (
        <StyledIndexSelectorItem onClick={handleClick}>
            <span>
                <Checkbox checked={isSelected} />
                <strong>{reference.name}</strong>
            </span>
            <span>
                Index Version <Label>{version}</Label>
            </span>
        </StyledIndexSelectorItem>
    );
};