import React from "react";
import { connect } from "react-redux";
import { Switch, Redirect, Route } from "react-router-dom";
import { LinkContainer } from "react-router-bootstrap";
import { Badge, Nav, NavItem, Breadcrumb } from "react-bootstrap";
import { get } from "lodash-es";
import IndexGeneral from "./General";
import IndexChanges from "./Changes";
import { getIndex, getIndexHistory } from "../actions";
import { LoadingPlaceholder, ViewHeader, RelativeTime, NotFound } from "../../base";

class IndexDetail extends React.Component {

    componentDidMount () {
        this.props.onGetIndex(this.props.match.params.indexId);
        this.props.onGetChanges(this.props.match.params.indexId, 1);
    }

    render () {

        if (this.props.error) {
            return <NotFound />;
        }

        if (this.props.detail === null) {
            return <LoadingPlaceholder />;
        }

        const indexId = this.props.detail.id;
        const { version, created_at, user } = this.props.detail;

        const refId = this.props.match.params.refId;

        return (
            <div>
                <Breadcrumb>
                    <Breadcrumb.Item>
                        <LinkContainer to={`/refs/${refId}/indexes`}>
                            <div>
                                Indexes
                            </div>
                        </LinkContainer>
                    </Breadcrumb.Item>
                    <Breadcrumb.Item active>
                        Index {version}
                    </Breadcrumb.Item>
                </Breadcrumb>

                <ViewHeader title={`Index ${version} - Indexes - Virtool`}>
                    <strong>Index {version}</strong>
                    <div className="text-muted" style={{fontSize: "12px"}}>
                        Created <RelativeTime time={created_at} /> by {user.id}
                    </div>
                </ViewHeader>

                <Nav bsStyle="tabs">
                    <LinkContainer to={`/refs/${refId}/indexes/${indexId}/general`}>
                        <NavItem>General</NavItem>
                    </LinkContainer>
                    <LinkContainer to={`/refs/${refId}/indexes/${indexId}/changes`}>
                        <NavItem>Changes  <Badge>{this.props.detail.change_count}</Badge></NavItem>
                    </LinkContainer>
                </Nav>

                <Switch>
                    <Redirect
                        from="/refs/:refId/indexes/:indexId"
                        to={`/refs/${refId}/indexes/${indexId}/general`}
                        exact
                    />
                    <Route path="/refs/:refId/indexes/:indexId/general" component={IndexGeneral} />
                    <Route path="/refs/:refId/indexes/:indexId/changes" component={IndexChanges} />
                </Switch>
            </div>
        );
    }

}

const mapStateToProps = (state) => ({
    error: get(state, "errors.GET_INDEX_ERROR", null),
    detail: state.indexes.detail
});

const mapDispatchToProps = (dispatch) => ({

    onGetIndex: (indexId) => {
        dispatch(getIndex(indexId));
    },

    onGetChanges: (indexId, page) => {
        dispatch(getIndexHistory(indexId, page));
    }

});

export default connect(mapStateToProps, mapDispatchToProps)(IndexDetail);
