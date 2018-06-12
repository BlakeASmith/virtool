import React from "react";
import Gauge from "react-svg-gauge";
import { map, mean, get } from "lodash-es";
import { connect } from "react-redux";
import { Flex, FlexItem, LoadingPlaceholder, NotFound } from "../../base";

import { getResources } from "../actions";

const color = "#d44b40";

class JobsResources extends React.Component {

    componentDidMount () {
        this.props.onGet();
        this.timer = window.setInterval(this.props.onGet, 800);
    }

    componentDidUpdate (prevProps) {
        if (!prevProps.error && this.props.error) {
            window.clearInterval(this.timer);
        }

        if (prevProps.error && !this.props.error) {
            window.setInterval(this.props.onGet, 800);
        }
    }

    componentWillUnmount () {
        window.clearInterval(this.timer);
    }

    render () {
        if (this.props.error) {
            return (
                <NotFound
                    status={this.props.error.status}
                    message={this.props.error.message}
                />
            );
        }

        if (this.props.resources === null) {
            return <LoadingPlaceholder />;
        }

        const coreGauges = map(this.props.resources.proc, (value, index) =>
            <Gauge
                key={index}
                color={color}
                value={Math.round(value)}
                label={`Core ${index + 1}`}
                width={100}
                height={80}
                minMaxLabelStyle={{display: "none"}}
            />
        );

        const used = (this.props.resources.mem.total - this.props.resources.mem.available) / 1000000000;

        const minMaxLabelStyle = {
            fontSize: "14px",
            fontColor: "#333333"
        };

        return (
            <div>
                <h3 style={{marginBottom: "30px"}}>
                    System Resources
                </h3>

                <h4 style={{display: "flex", alignItems: "center", marginTop: "20px"}} className="section-header">
                    <strong>CPU Utilization</strong>
                </h4>

                <Flex alignItems="center">
                    <FlexItem>
                        <Gauge
                            color={color}
                            value={Math.round(mean(this.props.resources.proc))}
                            label=""
                            width={200}
                            height={160}
                            minMaxLabelStyle={minMaxLabelStyle}
                        />
                    </FlexItem>

                    <FlexItem pad={25}>
                        <Flex wrap="wrap" justifyContent="center" alignContent="center">
                            {coreGauges}
                        </Flex>
                    </FlexItem>
                </Flex>

                <h4 style={{display: "flex", alignItems: "center", marginTop: "20px"}} className="section-header">
                    <strong>Memory Utilization (GB)</strong>
                </h4>

                <Gauge
                    color={color}
                    value={Math.round(used)}
                    label=""
                    minMaxLabelStyle={minMaxLabelStyle}
                    max={Math.round(this.props.resources.mem.total / 1000000000)}
                    width={200}
                    height={160}
                />

            </div>
        );
    }
}

const mapStateToProps = (state) => ({
    error: get(state, "errors.GET_RESOURCES_ERROR", null),
    resources: state.jobs.resources
});

const mapDispatchToProps = (dispatch) => ({

    onGet: () => {
        dispatch(getResources());
    }

});

export default connect(mapStateToProps, mapDispatchToProps)(JobsResources);
